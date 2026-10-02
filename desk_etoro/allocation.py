"""Portefeuille cible : sélection des tickers, poids, facteur multiplicateur (levier) et stops.

Poids : w_i ∝ (score_i/100) ** exposant_score / vol_i ** exposant_vol, puis plafonds par ligne,
plancher, plafond crypto et réserve de liquidités.
Levier : seulement pour une valeur à haut score ET adaptée au levier — classe d'actif admise,
volatilité modérée, tendance haussière (cours au-dessus des moyennes 50 et 200 jours), proche de
son plus haut 52 semaines, levier proposé par eToro sur ce compte. Le multiplicateur est le plus
grand levier permis tel que levier × volatilité ≤ vol_cible_position, puis l'exposition brute du
portefeuille est plafonnée. Une ligne à levier reçoit un stop (obligatoire chez eToro).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

from .config import Allocation
from .tickers import NoteTicker

CLASSES = {"stocks": "stocks", "etf": "etf", "crypto": "crypto", "forex": "currencies", "currencies": "currencies",
           "commodity": "commodities", "indices": "indices", "cfd": "cfd", "bonds": "bonds",
           "trustfunds": "trustfunds", "options": "options"}


def classe(meta: dict | None) -> str:
    return CLASSES.get(((meta or {}).get("type") or "").strip().lower(), "inconnue")


@dataclass
class Risque:
    dernier: float | None = None
    vol: float | None = None  # annualisée, rendements quotidiens log
    mm50: float | None = None
    mm200: float | None = None
    recul_52s: float | None = None  # cours / plus haut 52 semaines − 1
    momentum_6m: float | None = None

    @property
    def tendance_haussiere(self) -> bool | None:
        if self.dernier is None or self.mm50 is None or self.mm200 is None:
            return None
        return self.dernier > self.mm50 and self.dernier > self.mm200


def risque_depuis_cours(clotures: list[float], jours_par_an: int = 252) -> Risque:
    r = Risque()
    c = [x for x in clotures if x and x > 0]
    if not c:
        return r
    r.dernier = c[-1]
    fenetre = c[-(jours_par_an + 1):]
    if len(fenetre) >= 40:
        lr = [math.log(b / a) for a, b in zip(fenetre, fenetre[1:])]
        m = sum(lr) / len(lr)
        r.vol = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(jours_par_an)
    if len(c) >= 50:
        r.mm50 = sum(c[-50:]) / 50
    if len(c) >= 200:
        r.mm200 = sum(c[-200:]) / 200
    r.recul_52s = c[-1] / max(c[-jours_par_an:]) - 1
    if len(c) > 126:
        r.momentum_6m = c[-1] / c[-127] - 1
    return r


def leviers_permis(elig: dict | None, sens: str = "long") -> list[tuple[int, dict]]:
    """(levier, configuration eToro) proposés sans questionnaire supplémentaire, pour le sens donné."""
    out = []
    for cfg in (elig or {}).get("leverageConfigs") or []:
        if (cfg.get("direction") or "").lower() != sens or cfg.get("isPotential"):
            continue
        for lv in cfg.get("leverageValues") or []:
            out.append((int(lv), cfg))
    return sorted(out, key=lambda x: x[0])


@dataclass
class LigneCible:
    instrument_id: int
    symbol: str
    nom: str
    classe: str
    score: float
    rang: int
    sens: str = "long"
    poids: float = 0.0  # part du capital engagée (marge)
    levier: int = 1
    exposition: float = 0.0  # poids × levier
    cours: float | None = None
    vol: float | None = None
    stop: float | None = None
    stop_pct: float | None = None  # distance du stop en % du cours
    motif_levier: str = ""
    nb_detenteurs: int = 0
    consensus: float = 0.0
    largeur: float = 0.0
    detenu_avant: bool = False


@dataclass
class PortefeuilleCible:
    lignes: list[LigneCible] = field(default_factory=list)
    cash: float = 0.0
    exposition_brute: float = 0.0
    ecartes: list[tuple[str, str]] = field(default_factory=list)  # (ticker, motif) parmi les mieux notés


def _repartir(bruts: dict[int, float], total: float, plafond: float, plancher: float,
              fixes: dict[int, float] | None = None) -> dict[int, float]:
    """Répartit `total` au prorata de `bruts` en respectant [plancher, plafond] par ligne."""
    fixes = dict(fixes or {})
    libres = {k: v for k, v in bruts.items() if k not in fixes and v > 0}
    for _ in range(100):
        reste = total - sum(fixes.values())
        somme = sum(libres.values())
        if not libres or somme <= 0 or reste <= 0:
            break
        w = {k: reste * v / somme for k, v in libres.items()}
        hauts = {k for k, x in w.items() if x > plafond + 1e-12}
        bas = {k for k, x in w.items() if x < plancher - 1e-12}
        if not hauts and not bas:
            fixes.update(w)
            libres = {}
            break
        for k in hauts:
            fixes[k] = plafond
            libres.pop(k)
        if not hauts:  # on ne relève les petits qu'une fois les gros plafonnés
            for k in bas:
                fixes[k] = plancher
                libres.pop(k)
    for k in libres:
        fixes.setdefault(k, 0.0)
    somme = sum(fixes.values())
    if somme > total + 1e-9:  # planchers trop serrés : on revient au total demandé
        fixes = {k: v * total / somme for k, v in fixes.items()}
    return fixes


def ponderer(lignes: list[LigneCible], cfg: Allocation) -> float:
    """Fixe le poids de chaque ligne ; renvoie la part laissée en liquidités."""
    investi = max(0.0, 1.0 - cfg.reserve_cash)
    while lignes and cfg.poids_min * len(lignes) > investi:
        lignes.remove(min(lignes, key=lambda l: l.score))
    if not lignes:
        return 1.0
    vols = [l.vol for l in lignes if l.vol]
    vol_defaut = median(vols) if vols else 0.30
    bruts = {l.instrument_id: (l.score / 100) ** cfg.exposant_score / max(0.10, l.vol or vol_defaut) ** cfg.exposant_vol
             for l in lignes}
    poids = _repartir(bruts, investi, cfg.poids_max, cfg.poids_min)

    cryptos = [l.instrument_id for l in lignes if l.classe == "crypto"]
    part_crypto = sum(poids[i] for i in cryptos)
    if cryptos and part_crypto > cfg.poids_max_crypto + 1e-12:
        fixes = {i: poids[i] * cfg.poids_max_crypto / part_crypto for i in cryptos}
        poids = _repartir(bruts, investi, cfg.poids_max, cfg.poids_min, fixes)
    for l in lignes:
        l.poids = poids.get(l.instrument_id, 0.0)
    return max(0.0, 1.0 - sum(l.poids for l in lignes))


def appliquer_levier(l: LigneCible, elig: dict | None, risque: Risque, cfg: Allocation) -> None:
    motifs = []
    if l.score < cfg.score_levier:
        motifs.append(f"score {l.score:.0f} < {cfg.score_levier:.0f}")
    if l.classe not in cfg.classes_levier:
        motifs.append(f"classe {l.classe}")
    if risque.vol is None:
        motifs.append("volatilité inconnue")
    elif risque.vol > cfg.vol_max_levier:
        motifs.append(f"volatilité {risque.vol:.0%} > {cfg.vol_max_levier:.0%}")
    if risque.tendance_haussiere is False:
        motifs.append("sous ses moyennes 50/200 j")
    elif risque.tendance_haussiere is None:
        motifs.append("tendance inconnue")
    if risque.recul_52s is not None and risque.recul_52s < cfg.drawdown_max_levier:
        motifs.append(f"{risque.recul_52s:.0%} sous son plus haut")
    permis = [(lv, c) for lv, c in leviers_permis(elig, l.sens) if 2 <= lv <= cfg.levier_max]
    if elig is None:
        motifs.append("éligibilité eToro inconnue")
    elif not permis:
        motifs.append("levier non proposé par eToro")
    if motifs:
        l.levier, l.motif_levier = 1, " ; ".join(motifs)
        return
    adaptes = [lv for lv, _ in permis if lv * risque.vol <= cfg.vol_cible_position]
    if not adaptes:
        l.levier, l.motif_levier = 1, f"levier × vol > {cfg.vol_cible_position:.0%}"
        return
    l.levier = max(adaptes)
    l.motif_levier = f"x{l.levier} : score {l.score:.0f}, vol {risque.vol:.0%}, tendance haussière"


def poser_stop(l: LigneCible, elig: dict | None, cfg: Allocation) -> None:
    if l.levier <= 1 or not l.vol or not l.cours:
        l.stop = l.stop_pct = None
        return
    d = min(max(cfg.stop_sigma * l.vol / math.sqrt(52), cfg.stop_min), cfg.stop_max, 0.8 / l.levier)
    # eToro borne le stop en % de la marge (perte = distance × levier)
    for lv, c in leviers_permis(elig, l.sens):
        if lv == l.levier:
            mini, maxi = c.get("minStopLossPercentage"), c.get("maxStopLossPercentage")
            if mini:
                d = max(d, mini / 100 / l.levier)
            if maxi:
                d = min(d, maxi / 100 / l.levier)
            break
    l.stop_pct = d
    l.stop = round(l.cours * (1 - d) if l.sens == "long" else l.cours * (1 + d), 4)


def construire(notes: list[NoteTicker], instruments: dict[int, dict], eligibilites: dict[int, dict],
               risques: dict[int, Risque], detenus: dict[int, float], cfg: Allocation) -> PortefeuilleCible:
    cible = PortefeuilleCible()
    rang_max_detenu = math.ceil(cfg.hysteresis_rang * cfg.nb_lignes)
    negociables: list[NoteTicker] = []
    for t in notes:
        meta = instruments.get(t.instrument_id)
        sym = (meta or {}).get("symbol") or str(t.instrument_id)
        elig = eligibilites.get(t.instrument_id)
        motif = None
        if classe(meta) in cfg.classes_exclues:
            motif = f"classe {classe(meta)} exclue"
        elif t.sens == "court" and not cfg.autoriser_vente_a_decouvert:
            motif = "consensus vendeur"
        elif elig is not None and not elig.get("allowOpenPosition", True):
            motif = "ouverture impossible sur ce compte"
        if motif:
            if t.rang <= 3 * cfg.nb_lignes:
                cible.ecartes.append((sym, motif))
            continue
        negociables.append(t)

    gardes = [t for t in negociables if t.instrument_id in detenus and t.rang <= rang_max_detenu
              and t.score >= cfg.score_min - cfg.hysteresis_score][:cfg.nb_lignes]
    choisis = {t.instrument_id for t in gardes}
    for t in negociables:
        if len(choisis) >= cfg.nb_lignes:
            break
        if t.score >= cfg.score_min:
            choisis.add(t.instrument_id)
    selection = [t for t in negociables if t.instrument_id in choisis]

    lignes = []
    for t in selection:
        meta = instruments.get(t.instrument_id) or {}
        rq = risques.get(t.instrument_id) or Risque()
        lignes.append(LigneCible(
            instrument_id=t.instrument_id, symbol=meta.get("symbol") or str(t.instrument_id),
            nom=meta.get("nom") or "", classe=classe(meta), score=t.score, rang=t.rang, sens=t.sens,
            cours=rq.dernier, vol=rq.vol, nb_detenteurs=t.nb_detenteurs, consensus=t.consensus,
            largeur=t.largeur, detenu_avant=t.instrument_id in detenus))
    cible.cash = ponderer(lignes, cfg)
    for l in lignes:
        appliquer_levier(l, eligibilites.get(l.instrument_id), risques.get(l.instrument_id) or Risque(), cfg)

    # Plafond d'exposition brute : on retire d'abord le levier des lignes les moins bien notées
    def brute() -> float:
        return sum(l.poids * l.levier for l in lignes)
    while brute() > cfg.exposition_brute_max + 1e-9:
        a_levier = [l for l in lignes if l.levier > 1]
        if not a_levier:
            break
        l = min(a_levier, key=lambda x: x.score)
        permis = [lv for lv, _ in leviers_permis(eligibilites.get(l.instrument_id), l.sens) if 1 < lv < l.levier]
        l.levier = max(permis) if permis else 1
        l.motif_levier += " — réduit par le plafond d'exposition brute"

    for l in lignes:
        l.exposition = l.poids * l.levier
        poser_stop(l, eligibilites.get(l.instrument_id), cfg)
    cible.lignes = sorted(lignes, key=lambda l: -l.poids)
    cible.exposition_brute = brute()
    return cible
