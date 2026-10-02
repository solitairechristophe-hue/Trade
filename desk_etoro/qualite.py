"""Filtre de l'univers et note de qualité de chaque portefeuille.

Les critères viennent de trois sources :
  - eToro : la ligne de classement (performance, risque, régularité, copieurs, encours…) ;
  - calculés à partir des profits : série mensuelle de gains → Sharpe, Sortino, Calmar, volatilité,
    drawdown, Ulcer, stabilité de la courbe, part de mois positifs, pire mois ;
  - composition : diversification effective, part de positions gagnantes.
Chaque critère est converti en rang centile dans l'univers (insensible aux échelles et aux valeurs
extrêmes), les rangs sont moyennés par famille et les familles pondérées (config.Qualite).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import metriques
from .composition import Composition
from .config import Qualite, Univers

PALIERS = {"pi-cadet": 1, "pi-rising-star": 2, "pi-champion": 3, "pi-elite": 4, "pi-elite-pro": 5,
           "pi-certified": 5}

# nom, famille, source, plus haut = mieux, libellé
CRITERES: list[tuple[str, str, str, bool, str]] = [
    ("gain_1a", "performance", "eToro", True, "Gain sur la période de référence"),
    ("gain_6m", "performance", "eToro", True, "Gain 6 mois"),
    ("gain_3m", "performance", "eToro", True, "Gain 3 mois"),
    ("gain_2a", "performance", "eToro", True, "Gain depuis 2 ans civils"),
    ("rendement_annualise", "performance", "eToro", True, "Rendement annualisé"),
    ("cagr_36m", "performance", "calculé", True, "Rendement annualisé 36 mois"),
    ("sharpe", "ajuste_risque", "calculé", True, "Ratio de Sharpe"),
    ("sortino", "ajuste_risque", "calculé", True, "Ratio de Sortino"),
    ("calmar", "ajuste_risque", "calculé", True, "Ratio de Calmar (CAGR / drawdown max)"),
    ("gain_sur_creux", "ajuste_risque", "eToro", True, "Gain / pire recul (peakToValley)"),
    ("risk_score", "risque", "eToro", False, "Score de risque actuel"),
    ("max_daily_risk", "risque", "eToro", False, "Score de risque quotidien max"),
    ("max_monthly_risk", "risque", "eToro", False, "Score de risque mensuel max"),
    ("peak_to_valley", "risque", "eToro", True, "Pire recul de la période (%)"),
    ("daily_dd", "risque", "eToro", True, "Pire baisse quotidienne (%)"),
    ("weekly_dd", "risque", "eToro", True, "Pire baisse hebdomadaire (%)"),
    ("volatilite", "risque", "calculé", False, "Volatilité annualisée"),
    ("drawdown_max", "risque", "calculé", True, "Drawdown max 36 mois"),
    ("ulcer", "risque", "calculé", False, "Ulcer index"),
    ("levier_eleve", "risque", "eToro", False, "Part des trades à fort levier (%)"),
    ("diversification", "risque", "composition", True, "Nombre effectif de lignes"),
    ("mois_profitables", "regularite", "eToro", True, "Mois profitables (%)"),
    ("semaines_profitables", "regularite", "eToro", True, "Semaines profitables (%)"),
    ("win_ratio", "regularite", "eToro", True, "Trades gagnants (%)"),
    ("activite", "regularite", "eToro", True, "Semaines actives (%)"),
    ("mois_positifs_36m", "regularite", "calculé", True, "Mois positifs sur 36 mois"),
    ("stabilite", "regularite", "calculé", True, "Régularité de la courbe (R²)"),
    ("pire_mois", "regularite", "calculé", True, "Pire mois"),
    ("positions_gagnantes", "regularite", "composition", True, "Positions ouvertes gagnantes"),
    ("copieurs", "confiance", "eToro", True, "Nombre de copieurs"),
    ("croissance_copieurs", "confiance", "eToro", True, "Évolution des copieurs"),
    ("encours", "confiance", "eToro", True, "Encours copiés (AUM)"),
    ("anciennete", "confiance", "eToro", True, "Ancienneté (semaines)"),
    ("palier", "confiance", "eToro", True, "Palier Popular Investor"),
]
FAMILLES = ("performance", "ajuste_risque", "risque", "regularite", "confiance")


@dataclass
class NotePortefeuille:
    username: str
    ligne: dict  # ligne de classement eToro (période de référence)
    criteres: dict[str, float | None] = field(default_factory=dict)
    familles: dict[str, float] = field(default_factory=dict)
    qualite: float = 0.0  # 0 à 1
    vote: float = 0.0  # poids dans le croisement des tickers
    composition: Composition | None = None

    @property
    def palier(self) -> str:
        return self.ligne.get("subType") or ""


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def motif_exclusion(l: dict, u: Univers) -> str | None:
    """Raison d'écarter un portefeuille avant toute collecte détaillée, ou None s'il est retenu."""
    if l.get("type") not in (None, "trader"):
        return "pas un trader"
    if u.paliers_admis and (l.get("subType") or "") not in u.paliers_admis:
        return "palier non admis"
    gain = _f(l.get("gain"))
    if gain is None or gain <= -0.99:
        return "inactif ou sans historique"
    rs = int(l.get("riskScore") or 0)
    if rs < 1:
        return "pas de score de risque"
    if rs > u.risk_score_max:
        return f"risque {rs} > {u.risk_score_max}"
    if int(l.get("maxMonthlyRiskScore") or 0) > u.max_monthly_risk_max:
        return "pointe de risque mensuel trop haute"
    if int(l.get("weeksSinceRegistration") or 0) < u.anciennete_min_semaines:
        return "historique trop court"
    if (_f(l.get("activeWeeksPct")) or 0) < u.activite_min_pct:
        return "trop peu actif"
    if (_f(l.get("exposure")) or 0) < u.exposition_min_pct:
        return "trop peu investi"
    if (_f(l.get("highLeveragePct")) or 0) > u.levier_eleve_max_pct:
        return "usage excessif du levier"
    return None


def extraire(l: dict, compl: dict[str, dict], rendements: list[float], comp: Composition | None,
             taux_sans_risque: float) -> dict[str, float | None]:
    calc = metriques.toutes(rendements, 12, taux_sans_risque)
    gain = _f(l.get("gain"))
    ptv = _f(l.get("peakToValley"))
    c = {
        "gain_1a": gain,
        "gain_6m": _f((compl.get("SixMonthsAgo") or {}).get("gain")),
        "gain_3m": _f((compl.get("ThreeMonthsAgo") or {}).get("gain")),
        "gain_2a": _f((compl.get("LastTwoYears") or {}).get("gain")),
        "rendement_annualise": _f(l.get("annualizedReturn")),
        "cagr_36m": calc["cagr"] if len(rendements) >= 12 else None,
        "sharpe": calc["sharpe"],
        "sortino": calc["sortino"],
        "calmar": calc["calmar"],
        "gain_sur_creux": gain / abs(ptv / 100) if gain is not None and ptv and ptv < 0 else None,
        "risk_score": _f(l.get("riskScore")),
        "max_daily_risk": _f(l.get("maxDailyRiskScore")),
        "max_monthly_risk": _f(l.get("maxMonthlyRiskScore")),
        "peak_to_valley": ptv,
        "daily_dd": _f(l.get("dailyDD")),
        "weekly_dd": _f(l.get("weeklyDD")),
        "volatilite": calc["volatilite"],
        "drawdown_max": calc["drawdown_max"] if len(rendements) >= metriques.MIN_PERIODES else None,
        "ulcer": calc["ulcer"],
        "levier_eleve": _f(l.get("highLeveragePct")),
        "diversification": comp.nb_lignes_effectif if comp and comp.lignes else None,
        "mois_profitables": _f(l.get("profitableMonthsPct")),
        "semaines_profitables": _f(l.get("profitableWeeksPct")),
        "win_ratio": _f(l.get("winRatio")),
        "activite": _f(l.get("activeWeeksPct")),
        "mois_positifs_36m": calc["part_periodes_positives"],
        "stabilite": calc["stabilite"],
        "pire_mois": calc["pire_periode"] if len(rendements) >= metriques.MIN_PERIODES else None,
        "positions_gagnantes": comp.part_positions_gagnantes if comp else None,
        "copieurs": _f(l.get("copiers")),
        "croissance_copieurs": _f(l.get("copiersGain")),
        "encours": _f(l.get("aumValue")),
        "anciennete": _f(l.get("weeksSinceRegistration")),
        "palier": float(PALIERS.get(l.get("subType") or "", 0)),
    }
    # Indicateurs calculés présentés dans le rapport sans entrer dans la note
    c["volatilite_36m"] = calc["volatilite"]
    c["asymetrie"] = calc["asymetrie"]
    c["nb_mois"] = calc["nb_periodes"]
    return c


def noter(notes: list[NotePortefeuille], q: Qualite) -> None:
    """Remplit familles, qualité et vote de chaque portefeuille (en place)."""
    if not notes:
        return
    rangs: dict[str, dict[str, float]] = {}
    for nom, _fam, _src, haut, _lib in CRITERES:
        rangs[nom] = metriques.rang_percentile({n.username: n.criteres.get(nom) for n in notes}, haut)
    poids = {"performance": q.poids_performance, "ajuste_risque": q.poids_ajuste_risque,
             "risque": q.poids_risque, "regularite": q.poids_regularite, "confiance": q.poids_confiance}
    total_poids = sum(poids.values()) or 1.0
    for n in notes:
        for fam in FAMILLES:
            vals = [rangs[nom][n.username] for nom, f, *_ in CRITERES if f == fam and n.username in rangs[nom]]
            n.familles[fam] = sum(vals) / len(vals) if vals else 0.5
        n.qualite = sum(poids[f] * n.familles[f] for f in FAMILLES) / total_poids
        if n.composition is not None and not n.composition.lignes:
            n.qualite = 0.0  # rien à croiser : le portefeuille ne vote pas

    qualites = sorted(n.qualite for n in notes)
    seuil = qualites[min(len(qualites) - 1, int(q.quantile_min * len(qualites)))] if q.quantile_min > 0 else 0.0
    for n in notes:
        n.vote = n.qualite ** q.exposant if n.qualite >= seuil and n.qualite > 0 else 0.0
