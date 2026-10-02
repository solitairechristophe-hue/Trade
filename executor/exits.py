"""Décision de sortie d'une position ouverte (fonction pure, testée).

Le TP est posé chez IBKR (ordre limite GTC attaché à l'entrée). Le SL, le stop
du sous-jacent et la sortie temps sont surveillés par le robot : les ordres
stop sur combos d'options sont peu fiables chez IBKR.
"""
from __future__ import annotations

import datetime as dt

from .tickets import Ticket


def valeur_milieu(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2


def motif_sortie(t: Ticket, valeur: float | None, sous_jacent: float | None,
                 maintenant_ny: dt.datetime) -> str | None:
    if valeur is not None:
        if t.debit:
            if valeur <= t.stop_loss:
                return "SL"
            if valeur >= t.take_profit:
                return "TP"
        else:
            if valeur >= t.stop_loss:
                return "SL"
            if valeur <= t.take_profit:
                return "TP"
    # Invalidation de fond : clôture du sous-jacent au-delà du stop (vérifiée à partir de 15 h 55)
    if t.underlying_stop and sous_jacent and maintenant_ny.time() >= dt.time(15, 55):
        if (t.direction == "up" and sous_jacent < t.underlying_stop) or \
           (t.direction == "down" and sous_jacent > t.underlying_stop):
            return "STOP_SOUS_JACENT"
    if t.time_exit and maintenant_ny.date() >= t.time_exit and maintenant_ny.time() >= dt.time(10, 0):
        return "SORTIE_TEMPS"
    return None


def prix_sortie(t: Ticket, bid: float, ask: float) -> float:
    """Prix limite immédiatement exécutable : on vend au bid, on rachète à l'ask."""
    p = bid if t.exit_side == "SELL" else ask
    return round(max(p, 0.01), 2)
