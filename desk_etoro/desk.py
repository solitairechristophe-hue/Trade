"""Enchaînement d'un run du desk : univers → qualité → compositions → tickers → cible → ordres."""
from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from dataclasses import dataclass, field

from . import composition, qualite, tickers
from .allocation import PortefeuilleCible, Risque, construire, risque_depuis_cours
from .calendrier import NY, prochaine_revue
from .config import Config
from .qualite import NotePortefeuille
from .reequilibrage import Ordre, ordres, poids_detenus
from .sources import Collecteur
from .tickers import NoteTicker

log = logging.getLogger("desk_etoro")


@dataclass
class Resultat:
    date: str
    prochaine_revue: str
    univers: dict = field(default_factory=dict)
    portefeuilles: list[NotePortefeuille] = field(default_factory=list)
    tickers: list[NoteTicker] = field(default_factory=list)
    instruments: dict[int, dict] = field(default_factory=dict)
    risques: dict[int, Risque] = field(default_factory=dict)
    cible: PortefeuilleCible = field(default_factory=PortefeuilleCible)
    ordres: list[Ordre] = field(default_factory=list)


def alias_de_cotation(instruments: dict[int, dict]) -> dict[int, int]:
    """id d'une cotation secondaire (suffixe .RTH, séance régulière) → id de la cotation principale."""
    par_symbole = {(m.get("symbol") or "").upper(): i for i, m in instruments.items() if m.get("symbol")}
    alias = {}
    for i, m in instruments.items():
        sym = (m.get("symbol") or "").upper()
        if sym.endswith(".RTH") and sym[:-4] in par_symbole:
            alias[i] = par_symbole[sym[:-4]]
    return alias


def _composition(col: Collecteur, username: str, cfg: Config, jour: dt.date):
    """Composition depuis la source choisie, l'autre source servant de repli si la première manque."""
    def live():
        brut = col.portefeuille_live(username)
        return composition.analyser(brut, jour, cfg.tickers.jours_fraicheur, cfg.univers.inclure_copies) if brut else None

    def actifs():
        brut = col.actifs(username, cfg.tickers.jours_fraicheur + 7)
        return composition.depuis_actifs(brut, cfg.tickers.jours_fraicheur) if brut else None

    ordre = (actifs, live) if cfg.univers.source_composition == "actifs" else (live, actifs)
    for source in ordre:
        comp = source()
        if comp is not None and comp.lignes:
            return comp
    return None


def executer(cfg: Config, col: Collecteur, jour: dt.date, etat: dict) -> Resultat:
    u = cfg.univers
    debut = dt.datetime.combine(jour, dt.time(0, 0), NY)
    res = Resultat(date=jour.isoformat(), prochaine_revue=prochaine_revue(debut + dt.timedelta(days=1)).isoformat())

    # 1. Univers : tous les Popular Investors classés, puis filtres de risque / ancienneté / activité
    classement = col.classement(u.periode, u.popular_investor)
    if not classement:
        raise RuntimeError(f"classement {u.periode} vide ou indisponible")
    compl = {p: {l["username"].lower(): l for l in col.classement(p, u.popular_investor)}
             for p in u.periodes_complementaires}

    def complements(l: dict) -> dict[str, dict]:
        cle = l["username"].lower()
        return {p: rows[cle] for p, rows in compl.items() if cle in rows}

    exclusions: Counter = Counter()
    retenus = []
    for l in classement:
        motif = qualite.motif_exclusion(l, u)
        if motif:
            exclusions[motif] += 1
        else:
            retenus.append(l)
    log.info("%d portefeuilles classés, %d retenus après filtres", len(classement), len(retenus))

    # 2. Pré-qualité (classements seuls) pour ordonner la collecte et, au besoin, la limiter
    pre = [NotePortefeuille(l["username"], l, qualite.extraire(l, complements(l), [], None, cfg.qualite.taux_sans_risque))
           for l in retenus]
    qualite.noter(pre, cfg.qualite)
    pre.sort(key=lambda n: -n.qualite)
    if u.max_portefeuilles:
        pre = pre[:u.max_portefeuilles]

    # 3. Examen détaillé : historique des gains (critères calculés) et composition
    notes: list[NotePortefeuille] = []
    sans_composition = 0
    for i, p in enumerate(pre, 1):
        if i % 25 == 0:
            log.info("portefeuilles examinés : %d / %d", i, len(pre))
        comp = _composition(col, p.username, cfg, jour)
        if comp is None:
            sans_composition += 1
            continue
        rendements = [g for _, g in col.gains(p.username, "monthly", u.mois_historique)]
        notes.append(NotePortefeuille(p.username, p.ligne, qualite.extraire(
            p.ligne, complements(p.ligne), rendements, comp, cfg.qualite.taux_sans_risque), composition=comp))
    qualite.noter(notes, cfg.qualite)
    notes.sort(key=lambda n: -n.qualite)
    res.portefeuilles = notes

    # 4. Croisement des compositions et note des tickers (doublons de cotation fusionnés)
    detenus = poids_detenus(etat)
    ids = sorted({i for n in notes for i in n.composition.lignes} | set(detenus))
    res.instruments = col.instruments(ids)
    alias = alias_de_cotation(res.instruments)
    for n in notes:
        n.composition.fusionner(alias)
    res.tickers = tickers.noter(notes, cfg.tickers)

    # 5. Données de marché et conditions eToro pour la liste courte, puis portefeuille cible
    a = cfg.allocation
    courte = list(dict.fromkeys([t.instrument_id for t in res.tickers[:3 * a.nb_lignes]] + list(detenus)))
    eligibilites = col.eligibilite(courte)
    res.risques = {iid: risque_depuis_cours([c for _, c in col.cours(iid)]) for iid in courte}
    res.cible = construire(res.tickers, res.instruments, eligibilites, res.risques, detenus, a)
    res.ordres = ordres(etat, res.cible, a.capital, a.bande_reequilibrage)

    res.univers = {
        "periode": u.periode,
        "classes": len(classement),
        "exclus": dict(exclusions.most_common()),
        "retenus": len(retenus),
        "examines": len(pre),
        "sans_composition": sans_composition,
        "notes": len(notes),
        "votants": sum(1 for n in notes if n.vote > 0),
        "tickers_croises": len({i for n in notes if n.vote > 0 for i in n.composition.lignes}),
        "tickers_notes": len(res.tickers),
        "paliers": dict(Counter(n.palier or "?" for n in notes).most_common()),
    }
    return res
