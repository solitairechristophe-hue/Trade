"""Garde-fous avant tout envoi d'ordre. Un seul refus suffit à bloquer le ticket."""
from __future__ import annotations

from .config import Config
from .tickets import Ticket


def refus(t: Ticket, nav: float, risque_ouvert: float, ordres_du_jour: int,
          titres_occupes: set[str], cfg: Config) -> list[str]:
    r: list[str] = []
    if nav <= 0:
        return ["NAV inconnue"]
    if t.limit_price > t.price_cap:
        r.append(f"limite {t.limit_price} au-dessus du plafond {t.price_cap}")
    if t.max_loss > nav * cfg.risk_per_trade * (1 + cfg.risk_tolerance):
        r.append(f"risque {t.max_loss:.0f} $ > {cfg.risk_per_trade:.0%} de la NAV")
    if t.debit and t.premium > nav * cfg.max_premium_per_trade:
        r.append(f"prime {t.premium:.0f} $ > {cfg.max_premium_per_trade:.0%} de la NAV")
    if risque_ouvert + t.max_loss > nav * cfg.max_total_risk:
        r.append(f"risque cumulé {risque_ouvert + t.max_loss:.0f} $ > {cfg.max_total_risk:.0%} de la NAV")
    if ordres_du_jour >= cfg.max_new_orders_per_day:
        r.append(f"plafond de {cfg.max_new_orders_per_day} nouveaux ordres par jour atteint")
    if t.quantity > cfg.max_contracts_per_order:
        r.append(f"{t.quantity} contrats > maximum {cfg.max_contracts_per_order}")
    if t.symbol in titres_occupes:
        r.append(f"{t.symbol} a déjà une position ou un ordre du robot")
    return r
