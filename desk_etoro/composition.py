"""Composition d'un portefeuille à partir de son portefeuille live eToro.

Réponse de GET /api/v1/user-info/people/{username}/portfolio/live :
  positions[]     : positions ouvertes en direct (investmentPct = % du portefeuille investi
                    à l'ouverture, netProfit = P&L latent en %, isBuy, leverage, openTimestamp)
  socialTrades[]  : copies d'autres investisseurs, avec leurs propres positions[]
Le poids d'une position est sa valeur actuelle, investmentPct × (1 + netProfit/100),
rapportée à la valeur totale (positions directes + copies + liquidités non investies).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Ligne:
    """Exposition d'un portefeuille sur un instrument (poids en fraction de sa valeur)."""
    instrument_id: int
    poids_long: float = 0.0
    poids_court: float = 0.0
    poids_levier: float = 0.0  # part du poids détenue avec un levier > 1
    poids_recent: float = 0.0  # part du poids ouverte récemment
    pnl_pondere: float = 0.0  # Σ poids × P&L latent (%), à diviser par le poids total
    nb_positions: int = 0
    premiere_ouverture: str = ""

    @property
    def poids(self) -> float:
        return self.poids_long + self.poids_court

    @property
    def poids_net(self) -> float:
        return self.poids_long - self.poids_court

    @property
    def pnl_latent(self) -> float:
        return self.pnl_pondere / self.poids if self.poids else 0.0


@dataclass
class Composition:
    lignes: dict[int, Ligne] = field(default_factory=dict)
    part_investie: float = 0.0
    part_copies: float = 0.0  # poids des copies non détaillées
    nb_positions: int = 0
    concentration_hhi: float = 0.0
    nb_lignes_effectif: float = 0.0
    part_positions_gagnantes: float | None = None
    pnl_latent_moyen: float | None = None
    anciennete_moyenne_jours: float | None = None
    part_levier: float = 0.0
    part_court: float = 0.0
    source: str = "live"  # live (positions détaillées) ou actifs (répartition seule)

    def fusionner(self, alias: dict[int, int]) -> None:
        """Regroupe les lignes d'un même titre coté sous plusieurs identifiants (ex. AMZN et AMZN.RTH)."""
        for ancien, cible in alias.items():
            l = self.lignes.pop(ancien, None)
            if l is None:
                continue
            dest = self.lignes.setdefault(cible, Ligne(cible))
            for champ in ("poids_long", "poids_court", "poids_levier", "poids_recent", "pnl_pondere", "nb_positions"):
                setattr(dest, champ, getattr(dest, champ) + getattr(l, champ))
            if l.premiere_ouverture and (not dest.premiere_ouverture or l.premiere_ouverture < dest.premiere_ouverture):
                dest.premiere_ouverture = l.premiere_ouverture

    def resume(self) -> dict:
        return {
            "nb_instruments": len(self.lignes),
            "nb_positions": self.nb_positions,
            "part_investie": round(self.part_investie, 4),
            "part_copies": round(self.part_copies, 4),
            "concentration_hhi": round(self.concentration_hhi, 4),
            "nb_lignes_effectif": round(self.nb_lignes_effectif, 1),
            "part_positions_gagnantes": _r(self.part_positions_gagnantes),
            "pnl_latent_moyen_pct": _r(self.pnl_latent_moyen),
            "anciennete_moyenne_jours": _r(self.anciennete_moyenne_jours, 0),
            "part_levier": round(self.part_levier, 4),
            "part_court": round(self.part_court, 4),
            "source": self.source,
        }


def _r(x, n=4):
    return None if x is None else round(x, n)


def _date(ts: str | None) -> dt.date | None:
    if not ts:
        return None
    try:
        return dt.date.fromisoformat(ts[:10])
    except ValueError:
        return None


def _valeur(p: dict) -> float:
    inv = float(p.get("investmentPct") or 0.0)
    pnl = float(p.get("netProfit") or 0.0)
    return max(0.0, inv * (1 + pnl / 100))


def analyser(live: dict, aujourd_hui: dt.date, jours_fraicheur: int = 30,
             inclure_copies: bool = False) -> Composition:
    directes = list(live.get("positions") or [])
    copies = list(live.get("socialTrades") or [])

    # (position, valeur) de chaque position retenue, copies éventuellement « transparisées »
    retenues: list[tuple[dict, float]] = [(p, _valeur(p)) for p in directes]
    investi = sum(float(p.get("investmentPct") or 0.0) for p in directes)
    valeur_copies = 0.0
    for m in copies:
        investi += float(m.get("investmentPct") or 0.0)
        v_miroir = max(0.0, float(m.get("investmentPct") or 0.0) * (1 + float(m.get("netProfit") or 0.0) / 100))
        sous = list(m.get("positions") or [])
        total_sous = sum(_valeur(p) for p in sous)
        if inclure_copies and total_sous > 0:
            # On répartit la valeur ouverte de la copie au prorata des positions copiées
            ouvert = float(m.get("openInvestmentPct") or m.get("investmentPct") or 0.0)
            v_ouvert = max(0.0, ouvert * (1 + float(m.get("openNetProfit") or m.get("netProfit") or 0.0) / 100))
            retenues += [(p, _valeur(p) / total_sous * v_ouvert) for p in sous]
            valeur_copies += max(0.0, v_miroir - v_ouvert)
        else:
            valeur_copies += v_miroir

    cash = max(0.0, 100.0 - investi)
    total = sum(v for _, v in retenues) + valeur_copies + cash
    comp = Composition(nb_positions=len(retenues))
    if total <= 0:
        return comp

    limite = aujourd_hui - dt.timedelta(days=jours_fraicheur)
    gagnantes, ages, pnls = 0, [], []
    for p, v in retenues:
        iid = p.get("instrumentId")
        if iid is None:
            continue
        w = v / total
        ligne = comp.lignes.setdefault(int(iid), Ligne(int(iid)))
        if p.get("isBuy", True):
            ligne.poids_long += w
        else:
            ligne.poids_court += w
            comp.part_court += w
        if int(p.get("leverage") or 1) > 1:
            ligne.poids_levier += w
            comp.part_levier += w
        ouverture = _date(p.get("openTimestamp"))
        if ouverture and ouverture >= limite:
            ligne.poids_recent += w
        if ouverture:
            ages.append((aujourd_hui - ouverture).days)
            if not ligne.premiere_ouverture or ouverture.isoformat() < ligne.premiere_ouverture:
                ligne.premiere_ouverture = ouverture.isoformat()
        pnl = float(p.get("netProfit") or 0.0)
        ligne.pnl_pondere += w * pnl
        ligne.nb_positions += 1
        pnls.append(pnl)
        gagnantes += pnl > 0

    comp.part_investie = sum(l.poids for l in comp.lignes.values())
    comp.part_copies = valeur_copies / total
    if comp.part_investie > 0:
        parts = [l.poids / comp.part_investie for l in comp.lignes.values()]
        comp.concentration_hhi = sum(x * x for x in parts)
        comp.nb_lignes_effectif = 1 / comp.concentration_hhi if comp.concentration_hhi else 0.0
        comp.pnl_latent_moyen = sum(l.pnl_pondere for l in comp.lignes.values()) / comp.part_investie
    if pnls:
        comp.part_positions_gagnantes = gagnantes / len(pnls)
    if ages:
        comp.anciennete_moyenne_jours = sum(ages) / len(ages)
    return comp


def depuis_actifs(rep: dict, jours_fraicheur: int = 30) -> Composition:
    """Composition tirée de GET /api/v2/portfolios/{u}/assets/history (fractions, copies exclues).

    Plus légère que le portefeuille live mais sans sens ni levier. La fraîcheur est estimée par
    la hausse du montant investi (investedPct) depuis `jours_fraicheur` jours : une ligne nouvelle
    ou renforcée compte comme une entrée récente.
    """
    resultats = sorted((r for r in rep.get("results") or [] if r.get("date")), key=lambda r: r["date"])
    comp = Composition(source="actifs")
    if not resultats:
        return comp
    dernier = resultats[-1]
    limite = (dt.date.fromisoformat(dernier["date"][:10]) - dt.timedelta(days=jours_fraicheur)).isoformat()
    anciens = [r for r in resultats if r["date"][:10] <= limite]
    avant = None
    if anciens:
        avant = {int(a["instrumentId"]): float(a.get("investedPct") or 0.0)
                 for a in anciens[-1].get("assets") or [] if a.get("instrumentId") is not None}
    for a in dernier.get("assets") or []:
        w = float(a.get("valuePct") or 0.0)
        if w <= 0 or a.get("instrumentId") is None:
            continue
        iid = int(a["instrumentId"])
        ligne = comp.lignes.setdefault(iid, Ligne(iid))
        ligne.poids_long += w
        ligne.nb_positions += 1
        if avant is not None:
            investi, investi_avant = float(a.get("investedPct") or 0.0), avant.get(iid, 0.0)
            hausse = (investi - investi_avant) / investi if investi > 0 else 0.0
            if hausse > 0.05:  # en deçà : simple dérive de la base de calcul
                ligne.poids_recent += w * min(1.0, hausse)
    comp.source = "actifs" if avant is None else "actifs+historique"
    comp.nb_positions = sum(l.nb_positions for l in comp.lignes.values())
    comp.part_investie = sum(l.poids for l in comp.lignes.values())
    if comp.part_investie > 0:
        parts = [l.poids / comp.part_investie for l in comp.lignes.values()]
        comp.concentration_hhi = sum(x * x for x in parts)
        comp.nb_lignes_effectif = 1 / comp.concentration_hhi
    return comp
