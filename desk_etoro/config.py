"""Paramètres du desk eToro.

Valeurs par défaut ci-dessous, surchargeables par un fichier JSON (--config) dont les clés
reprennent les noms des sections et des champs, par exemple :
    {"univers": {"risk_score_max": 5}, "allocation": {"nb_lignes": 15}}
Les identifiants eToro se lisent uniquement dans l'environnement (jamais dans un fichier du dépôt).
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Univers:
    """Quels portefeuilles explorer et lesquels garder."""
    periode: str = "OneYearAgo"  # période de référence des classements eToro
    periodes_complementaires: tuple[str, ...] = ("ThreeMonthsAgo", "SixMonthsAgo", "LastTwoYears")
    popular_investor: bool = True  # « professionnels » = Popular Investors actifs
    paliers_admis: tuple[str, ...] = ()  # vide = tous ; ex. ("pi-elite-pro", "pi-certified")
    risk_score_max: int = 6
    max_monthly_risk_max: int = 7
    anciennete_min_semaines: int = 52
    activite_min_pct: float = 50.0  # activeWeeksPct
    exposition_min_pct: float = 20.0  # part investie du portefeuille
    levier_eleve_max_pct: float = 50.0  # highLeveragePct au-delà duquel le portefeuille est écarté
    max_portefeuilles: int = 0  # 0 = tous les éligibles ; sinon les N meilleurs en pré-qualité
    inclure_copies: bool = False  # transparence sur les positions copiées (socialTrades)
    alias_symboles: dict = field(default_factory=lambda: {"GOOGL": "GOOG"})  # classes d'actions d'un même émetteur
    source_composition: str = "live"  # live (positions détaillées) ou actifs (répartition, plus léger)
    mois_historique: int = 36  # gains mensuels utilisés pour les critères calculés


@dataclass
class Qualite:
    """Poids des familles de critères dans la note de qualité d'un portefeuille (somme = 1)."""
    poids_performance: float = 0.25
    poids_ajuste_risque: float = 0.25
    poids_risque: float = 0.20
    poids_regularite: float = 0.15
    poids_confiance: float = 0.15
    exposant: float = 2.0  # q = Q ** exposant : accentue l'écart entre bons et très bons
    quantile_min: float = 0.25  # les 25 % les moins bien notés ne votent pas
    taux_sans_risque: float = 0.04


@dataclass
class Tickers:
    """Croisement des compositions et note des tickers (poids des composantes, somme = 1)."""
    poids_consensus: float = 0.35  # poids moyen pondéré par la qualité (tous portefeuilles)
    poids_largeur: float = 0.30  # part (pondérée qualité) des portefeuilles qui détiennent
    poids_conviction: float = 0.15  # poids moyen chez les détenteurs
    poids_qualite_detenteurs: float = 0.12
    poids_fraicheur: float = 0.08  # entrées récentes des détenteurs
    jours_fraicheur: int = 30
    detenteurs_min: int = 3


@dataclass
class Allocation:
    """Construction du portefeuille cible et facteur de levier."""
    nb_lignes: int = 20
    score_min: float = 60.0
    score_plancher_poids: float = 50.0  # poids ∝ ((score − plancher)/(100 − plancher)) ** exposant_score
    exposant_score: float = 1.5  # … / vol ** exposant_vol
    exposant_vol: float = 0.5
    poids_max: float = 0.10
    poids_min: float = 0.02
    poids_max_crypto: float = 0.15  # total des cryptomonnaies
    reserve_cash: float = 0.02
    autoriser_vente_a_decouvert: bool = False
    classes_exclues: tuple[str, ...] = ("currencies",)
    # Facteur multiplicateur (levier)
    levier_max: int = 2
    score_levier: float = 70.0  # « haut score » : score minimal pour envisager le levier…
    rang_max_levier: int = 10  # … et rang parmi les tickers notés
    vol_max_levier: float = 0.35  # volatilité annualisée maximale de l'actif
    vol_cible_position: float = 0.60  # levier × vol ne dépasse pas ce niveau (≈ vol des valeurs les plus nerveuses détenues sans levier)
    drawdown_max_levier: float = -0.25  # recul maximal depuis le plus haut 52 semaines
    classes_levier: tuple[str, ...] = ("stocks", "etf", "indices")
    exposition_brute_max: float = 1.5  # somme des poids × levier
    stop_sigma: float = 2.5  # distance du stop = stop_sigma × vol hebdomadaire
    stop_min: float = 0.08
    stop_max: float = 0.30
    # Revue hebdomadaire
    hysteresis_rang: float = 1.5  # une ligne détenue reste si son rang ≤ 1,5 × nb_lignes
    hysteresis_score: float = 10.0  # … et si son score ≥ score_min − 10
    bande_reequilibrage: float = 0.01  # écart de poids sous lequel on ne touche pas une ligne
    capital: float = 10000.0  # montant de référence pour chiffrer les ordres (devise du compte)


@dataclass
class Connexion:
    """Accès à l'API publique eToro (clé utilisateur + clé application) ou au serveur MCP."""
    mode: str = "rest"  # rest | mcp
    base_rest: str = "https://public-api.etoro.com"
    url_mcp: str = "https://mcp.public-api.etoro.com"
    x_api_key: str = ""
    x_user_key: str = ""
    bearer: str = ""
    timeout: float = 60.0


@dataclass
class Config:
    univers: Univers = field(default_factory=Univers)
    qualite: Qualite = field(default_factory=Qualite)
    tickers: Tickers = field(default_factory=Tickers)
    allocation: Allocation = field(default_factory=Allocation)
    connexion: Connexion = field(default_factory=Connexion)
    dossier_donnees: Path = Path("data/desk_etoro")

    @classmethod
    def charger(cls, chemin: Path | None = None) -> "Config":
        cfg = cls()
        if chemin:
            _appliquer(cfg, json.loads(Path(chemin).read_text(encoding="utf-8")))
        env = os.environ
        c = cfg.connexion
        c.mode = env.get("ETORO_MODE", c.mode)
        c.base_rest = env.get("ETORO_API_BASE", c.base_rest)
        c.url_mcp = env.get("ETORO_MCP_URL", c.url_mcp)
        c.x_api_key = env.get("ETORO_API_KEY", c.x_api_key)
        c.x_user_key = env.get("ETORO_USER_KEY", c.x_user_key)
        c.bearer = env.get("ETORO_BEARER", c.bearer)
        if env.get("DESK_ETORO_DATA"):
            cfg.dossier_donnees = Path(env["DESK_ETORO_DATA"])
        if env.get("DESK_ETORO_CAPITAL"):
            cfg.allocation.capital = float(env["DESK_ETORO_CAPITAL"])
        return cfg

    def en_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["dossier_donnees"] = str(self.dossier_donnees)
        d["connexion"] = {k: v for k, v in d["connexion"].items() if k in ("mode", "base_rest", "url_mcp")}
        return d


def _appliquer(cfg: Config, surcharges: dict) -> None:
    for section, valeurs in surcharges.items():
        if section == "dossier_donnees":
            cfg.dossier_donnees = Path(valeurs)
            continue
        cible = getattr(cfg, section, None)
        if cible is None or not dataclasses.is_dataclass(cible) or not isinstance(valeurs, dict):
            raise ValueError(f"section de configuration inconnue : {section}")
        noms = {f.name: f for f in dataclasses.fields(cible)}
        for nom, valeur in valeurs.items():
            if nom not in noms:
                raise ValueError(f"paramètre inconnu : {section}.{nom}")
            if isinstance(getattr(cible, nom), tuple):
                valeur = tuple(valeur)
            setattr(cible, nom, valeur)
