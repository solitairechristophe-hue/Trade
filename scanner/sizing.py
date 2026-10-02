"""Taille des positions et classement par espérance de gain (fonctions pures)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .structure import Proposition


@dataclass(frozen=True)
class Dimensionnee:
    prop: Proposition
    score: float
    quantity: int
    p_win: float
    ev: float  # espérance de gain en $ pour la position
    ev_ratio: float  # espérance par $ risqué
    max_loss: float
    premium: float

    @property
    def rr(self) -> float:
        return self.prop.max_gain_per_contract / max(self.prop.max_loss_per_contract, 1e-9)


P_MIN, P_MAX = 0.38, 0.62  # défaut prudent, remplacé par la calibration si elle existe


def charger_calibration(chemin: Path) -> tuple[float, float] | None:
    """(p au seuil, p au score maximal) mesurés par scanner.calibrate, bornés à [0,30 ; 0,70]."""
    try:
        d = json.loads(chemin.read_text(encoding="utf-8"))
        lo, hi = float(d["p_min"]), float(d["p_max"])
    except Exception:
        return None
    lo, hi = max(0.30, min(0.70, lo)), max(0.30, min(0.70, hi))
    return (lo, max(lo, hi))


def rendement_setup(chemin: Path, setup: str) -> float | None:
    """Rendement moyen mesuré (multiple de la prime) d'un setup, depuis la calibration."""
    try:
        return float(json.loads(chemin.read_text(encoding="utf-8"))["setups"][setup]["rendement_moyen"])
    except Exception:
        return None


def probabilite(score: float, calib: tuple[float, float] | None = None) -> float:
    """Probabilité de gain : interpolation linéaire entre p_min (score 0) et p_max (score 100)."""
    lo, hi = calib or (P_MIN, P_MAX)
    return round(lo + (hi - lo) * max(0.0, min(1.0, score / 100)), 3)


def quantite(prop: Proposition, nav: float, risk_per_trade: float, max_premium_per_trade: float,
             max_contracts: int, risque_restant: float) -> int:
    budget_risque = min(nav * risk_per_trade, risque_restant)
    q = math.floor(budget_risque / prop.max_loss_per_contract)
    if prop.side == "BUY":
        q = min(q, math.floor(nav * max_premium_per_trade / prop.premium_per_contract))
    return max(0, min(q, max_contracts))


def dimensionner(prop: Proposition, score: float, nav: float, *, risk_per_trade: float,
                 max_premium_per_trade: float, max_contracts: int, risque_restant: float,
                 calib: tuple[float, float] | None = None, rendement: float | None = None,
                 taille_essai: int = 0) -> Dimensionnee | None:
    """`rendement` : espérance mesurée en backtest pour ce setup (multiple de la prime) ; elle remplace le
    modèle binaire TP/SL, qui ignore que la plupart des pertes sont partielles. `taille_essai` > 0 plafonne
    la quantité tant que le setup n'est pas prouvé en réel."""
    q = quantite(prop, nav, risk_per_trade, max_premium_per_trade, max_contracts, risque_restant)
    if taille_essai:
        q = min(q, taille_essai)
    if q < 1:
        return None
    p = probabilite(score, calib)
    gain, perte = prop.max_gain_per_contract * q, prop.max_loss_per_contract * q
    if rendement is not None:
        ev = rendement * prop.premium_per_contract * q
    else:
        ev = p * gain - (1 - p) * perte
    return Dimensionnee(prop=prop, score=score, quantity=q, p_win=p, ev=round(ev, 2),
                        ev_ratio=round(ev / perte, 3), max_loss=round(perte, 2),
                        premium=round(prop.premium_per_contract * q, 2))


def classer(items: list[Dimensionnee]) -> list[Dimensionnee]:
    """Les plus rentables d'abord : espérance par $ risqué, puis score."""
    return sorted(items, key=lambda d: (d.ev_ratio, d.score), reverse=True)
