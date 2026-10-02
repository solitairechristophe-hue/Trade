"""Croisement des compositions : note de chaque ticker détenu par les portefeuilles qui votent.

Pour un instrument i et des portefeuilles p de vote q_p (qualité ** exposant) et de poids w_p,i :
  consensus      = Σ q_p·w_p,i / Σ q_p           poids qu'aurait i dans la copie pondérée de tous
  largeur        = Σ_{p détient i} q_p / Σ q_p    part (pondérée qualité) des portefeuilles qui le détiennent
  conviction     = Σ_{p détient i} q_p·w_p,i / Σ_{p détient i} q_p   poids moyen chez ses détenteurs
  qualité dét.   = moyenne des qualités des détenteurs
  fraîcheur      = part du poids des détenteurs ouverte depuis moins de N jours (si connue)
Le score (0–100) pondère ces composantes ramenées sur [0, 1] parmi les tickers assez détenus :
échelle logarithmique pour consensus, largeur et conviction (de grandeurs très étalées), linéaire
pour la qualité des détenteurs et la fraîcheur, chacune entre son quantile 2 % et son maximum.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import metriques
from .config import Tickers
from .qualite import NotePortefeuille


@dataclass
class NoteTicker:
    instrument_id: int
    nb_detenteurs: int = 0
    consensus: float = 0.0  # poids net (long − court) pondéré qualité
    consensus_long: float = 0.0
    consensus_court: float = 0.0
    largeur: float = 0.0
    conviction: float = 0.0
    qualite_detenteurs: float = 0.0
    fraicheur: float | None = None
    part_levier_detenteurs: float = 0.0
    pnl_latent_moyen: float = 0.0
    score: float = 0.0
    rang: int = 0
    composantes: dict[str, float] = field(default_factory=dict)
    detenteurs: list[tuple[str, float, float]] = field(default_factory=list)  # (username, poids, qualité)

    @property
    def sens(self) -> str:
        return "long" if self.consensus_long >= self.consensus_court else "court"


def noter(portefeuilles: list[NotePortefeuille], cfg: Tickers) -> list[NoteTicker]:
    votants = [p for p in portefeuilles if p.vote > 0 and p.composition and p.composition.lignes]
    total_vote = sum(p.vote for p in votants)
    if total_vote <= 0:
        return []

    notes: dict[int, NoteTicker] = {}
    acc_recent: dict[int, list[float]] = {}  # [Σ q·poids récent, Σ q·poids] pour la fraîcheur
    for p in votants:
        detail = p.composition.source in ("live", "actifs+historique")  # fraîcheur connue
        for iid, l in p.composition.lignes.items():
            if l.poids <= 0:
                continue
            t = notes.setdefault(iid, NoteTicker(iid))
            t.nb_detenteurs += 1
            t.consensus_long += p.vote * l.poids_long
            t.consensus_court += p.vote * l.poids_court
            t.largeur += p.vote
            t.qualite_detenteurs += p.qualite
            t.part_levier_detenteurs += p.vote * l.poids_levier
            t.pnl_latent_moyen += p.vote * l.poids * l.pnl_latent
            t.detenteurs.append((p.username, l.poids_net, p.qualite))
            if detail:
                a = acc_recent.setdefault(iid, [0.0, 0.0])
                a[0] += p.vote * l.poids_recent
                a[1] += p.vote * l.poids

    for t in notes.values():
        somme_q_detenteurs = t.largeur
        poids_detenteurs = t.consensus_long + t.consensus_court
        t.conviction = (t.consensus_long - t.consensus_court) / somme_q_detenteurs
        t.qualite_detenteurs /= t.nb_detenteurs
        t.part_levier_detenteurs = t.part_levier_detenteurs / poids_detenteurs if poids_detenteurs else 0.0
        t.pnl_latent_moyen = t.pnl_latent_moyen / poids_detenteurs if poids_detenteurs else 0.0
        t.consensus_long /= total_vote
        t.consensus_court /= total_vote
        t.consensus = t.consensus_long - t.consensus_court
        t.largeur /= total_vote
        a = acc_recent.get(t.instrument_id)
        t.fraicheur = a[0] / a[1] if a and a[1] > 0 else None
        t.detenteurs.sort(key=lambda d: -abs(d[1]) * d[2])

    retenus = [t for t in notes.values() if t.nb_detenteurs >= cfg.detenteurs_min]
    composantes = {  # nom : (poids, valeurs, échelle log)
        "consensus": (cfg.poids_consensus, {t.instrument_id: abs(t.consensus) for t in retenus}, True),
        "largeur": (cfg.poids_largeur, {t.instrument_id: t.largeur for t in retenus}, True),
        "conviction": (cfg.poids_conviction, {t.instrument_id: abs(t.conviction) for t in retenus}, True),
        "qualite_detenteurs": (cfg.poids_qualite_detenteurs,
                               {t.instrument_id: t.qualite_detenteurs for t in retenus}, False),
        "fraicheur": (cfg.poids_fraicheur, {t.instrument_id: t.fraicheur for t in retenus}, False),
    }
    rangs = {nom: metriques.echelle(vals, log) for nom, (_, vals, log) in composantes.items()}
    for t in retenus:
        total, poids_utiles = 0.0, 0.0
        for nom, (poids, _, _) in composantes.items():
            r = rangs[nom].get(t.instrument_id)
            if r is None:  # fraîcheur inconnue : la composante est ignorée, les autres repondérées
                continue
            t.composantes[nom] = r
            total += poids * r
            poids_utiles += poids
        t.score = 100 * total / poids_utiles if poids_utiles else 0.0

    retenus.sort(key=lambda t: (-t.score, -t.consensus))
    for i, t in enumerate(retenus, 1):
        t.rang = i
    return retenus
