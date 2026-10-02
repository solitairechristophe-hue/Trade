"""Prix de la volatilité : IV payée face à une prévision de volatilité réalisée (HAR, Corsi 2009).

Sans données intraday, la variance réalisée d'une séance est approchée par le rendement logarithmique au carré.
Prévision de la variance quotidienne moyenne des semaines suivantes :
    v̂ = c + b_j·RV_jour + b_s·RV_semaine(5) + b_m·RV_mois(22)
avec les coefficients typiques de la littérature (b_j 0,36 ; b_s 0,28 ; b_m 0,28) et c = 0,08 × variance moyenne
de tout l'historique disponible (retour vers la moyenne). Volatilité annualisée = √(252 · v̂).
Le ratio IV30 / prévision mesure ce que l'option fait payer au-delà de la volatilité attendue (prime de variance).
"""
from __future__ import annotations

import math

B_JOUR, B_SEMAINE, B_MOIS, B_LONG = 0.36, 0.28, 0.28, 0.08


def rendements_carres(clotures: list[float]) -> list[float]:
    return [math.log(b / a) ** 2 for a, b in zip(clotures, clotures[1:]) if a > 0 and b > 0]


def prevision_har(clotures: list[float]) -> float | None:
    """Volatilité annualisée prévue, à partir des clôtures jusqu'à la date de décision incluse (≥ 23 clôtures)."""
    r2 = rendements_carres(clotures)
    if len(r2) < 22:
        return None
    v = (B_JOUR * r2[-1] + B_SEMAINE * sum(r2[-5:]) / 5 + B_MOIS * sum(r2[-22:]) / 22
         + B_LONG * sum(r2) / len(r2))
    return math.sqrt(252 * v)


def ratio_iv(iv30: float | None, clotures: list[float]) -> float | None:
    """IV30 / volatilité prévue. > 1 : l'option fait payer plus que la volatilité attendue."""
    p = prevision_har(clotures)
    if not iv30 or not p:
        return None
    iv = iv30 / 100 if iv30 > 3 else iv30
    return iv / p
