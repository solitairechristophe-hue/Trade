"""Taille des positions et classement par espérance de gain (fonctions pures)."""
from __future__ import annotations

import math
from dataclasses import dataclass

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


def probabilite(score: float) -> float:
    """Estimation prudente : 38 % à score 0, ~62 % à score 100 (jamais au-dessus)."""
    return round(0.38 + 0.24 * max(0.0, min(1.0, score / 100)), 3)


def quantite(prop: Proposition, nav: float, risk_per_trade: float, max_premium_per_trade: float,
             max_contracts: int, risque_restant: float) -> int:
    budget_risque = min(nav * risk_per_trade, risque_restant)
    q = math.floor(budget_risque / prop.max_loss_per_contract)
    if prop.side == "BUY":
        q = min(q, math.floor(nav * max_premium_per_trade / prop.premium_per_contract))
    return max(0, min(q, max_contracts))


def dimensionner(prop: Proposition, score: float, nav: float, *, risk_per_trade: float,
                 max_premium_per_trade: float, max_contracts: int, risque_restant: float) -> Dimensionnee | None:
    q = quantite(prop, nav, risk_per_trade, max_premium_per_trade, max_contracts, risque_restant)
    if q < 1:
        return None
    p = probabilite(score)
    gain, perte = prop.max_gain_per_contract * q, prop.max_loss_per_contract * q
    ev = p * gain - (1 - p) * perte
    return Dimensionnee(prop=prop, score=score, quantity=q, p_win=p, ev=round(ev, 2),
                        ev_ratio=round(ev / perte, 3), max_loss=round(perte, 2),
                        premium=round(prop.premium_per_contract * q, 2))


def classer(items: list[Dimensionnee]) -> list[Dimensionnee]:
    """Les plus rentables d'abord : espérance par $ risqué, puis score."""
    return sorted(items, key=lambda d: (d.ev_ratio, d.score), reverse=True)
