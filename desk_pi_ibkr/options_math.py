"""Mathématiques des options, en Python standard (sans numpy ni scipy).

Conventions : temps en années, taux et dividende en taux continus annuels (r, q), volatilité annualisée.
Prix par action (multiplier par 100 pour un contrat US). theta est donné par jour calendaire, vega pour
1 point de volatilité (0,01), rho pour 1 point de taux.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)


def ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _d1d2(s: float, k: float, t: float, r: float, q: float, vol: float) -> tuple[float, float]:
    vt = vol * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * vol * vol) * t) / vt
    return d1, d1 - vt


def valeur_intrinseque(s: float, k: float, droit: str) -> float:
    return max(0.0, s - k) if droit == "C" else max(0.0, k - s)


def bs_prix(s: float, k: float, t: float, r: float, q: float, vol: float, droit: str) -> float:
    """Prix Black-Scholes-Merton européen (droit "C" ou "P")."""
    if t <= 0 or vol <= 0:
        return valeur_intrinseque(s * math.exp(-q * max(t, 0)), k * math.exp(-r * max(t, 0)), droit)
    d1, d2 = _d1d2(s, k, t, r, q, vol)
    if droit == "C":
        return s * math.exp(-q * t) * ncdf(d1) - k * math.exp(-r * t) * ncdf(d2)
    return k * math.exp(-r * t) * ncdf(-d2) - s * math.exp(-q * t) * ncdf(-d1)


@dataclass(frozen=True)
class Grecques:
    prix: float
    delta: float
    gamma: float
    vega: float  # par point de volatilité
    theta: float  # par jour calendaire
    rho: float  # par point de taux


def bs_grecques(s: float, k: float, t: float, r: float, q: float, vol: float, droit: str) -> Grecques:
    if t <= 0 or vol <= 0:
        itm = (s > k) if droit == "C" else (s < k)
        d = (1.0 if itm else 0.0) * (1 if droit == "C" else -1)
        return Grecques(valeur_intrinseque(s, k, droit), d, 0.0, 0.0, 0.0, 0.0)
    d1, d2 = _d1d2(s, k, t, r, q, vol)
    eq, er, rt = math.exp(-q * t), math.exp(-r * t), math.sqrt(t)
    gamma = eq * npdf(d1) / (s * vol * rt)
    vega = s * eq * npdf(d1) * rt / 100
    if droit == "C":
        prix = s * eq * ncdf(d1) - k * er * ncdf(d2)
        delta = eq * ncdf(d1)
        theta = (-s * eq * npdf(d1) * vol / (2 * rt) - r * k * er * ncdf(d2) + q * s * eq * ncdf(d1)) / 365
        rho = k * t * er * ncdf(d2) / 100
    else:
        prix = k * er * ncdf(-d2) - s * eq * ncdf(-d1)
        delta = -eq * ncdf(-d1)
        theta = (-s * eq * npdf(d1) * vol / (2 * rt) + r * k * er * ncdf(-d2) - q * s * eq * ncdf(-d1)) / 365
        rho = -k * t * er * ncdf(-d2) / 100
    return Grecques(prix, delta, gamma, vega, theta, rho)


def prix_americain(s: float, k: float, t: float, r: float, q: float, vol: float, droit: str,
                   pas: int = 200) -> float:
    """Prix américain par arbre binomial CRR (exercice anticipé possible à chaque pas)."""
    if t <= 0 or vol <= 0:
        return valeur_intrinseque(s, k, droit)
    dt = t / pas
    u = math.exp(vol * math.sqrt(dt))
    d = 1 / u
    a = math.exp((r - q) * dt)
    p = (a - d) / (u - d)
    if not 0 < p < 1:  # pas trop grands au regard du portage : on raffine
        return prix_americain(s, k, t, r, q, vol, droit, pas * 2) if pas < 3200 else bs_prix(s, k, t, r, q, vol, droit)
    actu = math.exp(-r * dt)
    signe = 1 if droit == "C" else -1
    valeurs = [max(0.0, signe * (s * u ** (pas - 2 * i) - k)) for i in range(pas + 1)]
    for n in range(pas - 1, -1, -1):
        for i in range(n + 1):
            continuation = actu * (p * valeurs[i] + (1 - p) * valeurs[i + 1])
            exercice = signe * (s * u ** (n - 2 * i) - k)
            valeurs[i] = max(continuation, exercice)
    return valeurs[0]


def iv_implicite(prix: float, s: float, k: float, t: float, r: float, q: float, droit: str,
                 bas: float = 1e-4, haut: float = 5.0, tol: float = 1e-7) -> float | None:
    """Volatilité implicite européenne par Newton protégé par bissection ; None si le prix est hors bornes."""
    if t <= 0 or prix <= 0:
        return None
    mini = bs_prix(s, k, t, r, q, bas, droit)
    maxi = bs_prix(s, k, t, r, q, haut, droit)
    if not mini - 1e-9 <= prix <= maxi + 1e-9:
        return None
    vol = 0.3
    for _ in range(100):
        g = bs_grecques(s, k, t, r, q, vol, droit)
        ecart = g.prix - prix
        if abs(ecart) < tol:
            return vol
        if ecart > 0:
            haut = vol
        else:
            bas = vol
        vega = g.vega * 100
        nouveau = vol - ecart / vega if vega > 1e-10 else None
        vol = nouveau if nouveau is not None and bas < nouveau < haut else 0.5 * (bas + haut)
    return vol


def proba_finir_au_dela(s: float, k: float, t: float, mu: float, q: float, vol: float, au_dessus: bool = True) -> float:
    """Probabilité que le cours finisse au-dessus (ou en dessous) de k à l'horizon t, sous une dérive mu."""
    if t <= 0 or vol <= 0:
        return 1.0 if (s > k) == au_dessus else 0.0
    d2 = (math.log(s / k) + (mu - q - 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    return ncdf(d2) if au_dessus else ncdf(-d2)


def proba_toucher(s: float, barriere: float, t: float, mu: float, q: float, vol: float) -> float:
    """Probabilité que le cours touche la barrière avant t (mouvement brownien géométrique, surveillance continue)."""
    if barriere == s:
        return 1.0
    if t <= 0 or vol <= 0:
        return 0.0
    nu = mu - q - 0.5 * vol * vol
    b = math.log(barriere / s)
    st = vol * math.sqrt(t)
    if b > 0:
        p = ncdf((-b + nu * t) / st) + math.exp(2 * nu * b / (vol * vol)) * ncdf((-b - nu * t) / st)
    else:
        p = ncdf((b - nu * t) / st) + math.exp(2 * nu * b / (vol * vol)) * ncdf((b + nu * t) / st)
    return min(1.0, max(0.0, p))


def noeuds_normale(n: int = 121, borne: float = 6.0) -> list[tuple[float, float]]:
    """Quadrature de la loi normale centrée réduite : (z, poids), poids sommant à 1 (règle de Simpson)."""
    if n % 2 == 0:
        n += 1
    h = 2 * borne / (n - 1)
    points = []
    for i in range(n):
        z = -borne + i * h
        coef = 1 if i in (0, n - 1) else (4 if i % 2 else 2)
        points.append((z, coef * npdf(z) * h / 3))
    total = sum(w for _, w in points)
    return [(z, w / total) for z, w in points]


def cours_scenarios(s: float, h: float, mu: float, q: float, vol: float,
                    saut: float = 0.0, noeuds: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Cours du sous-jacent à l'horizon h (années) et probabilités.

    Loi log-normale de dérive mu et de volatilité vol ; `saut` ajoute un choc de résultats symétrique
    (mouvement lognormal d'écart-type `saut`), combiné à la diffusion en variance.
    """
    noeuds = noeuds or noeuds_normale()
    var = vol * vol * h + saut * saut
    sd = math.sqrt(max(var, 1e-12))
    m = (mu - q) * h - 0.5 * var
    return [(s * math.exp(m + sd * z), w) for z, w in noeuds]


def esperance(scenarios: list[tuple[float, float]], gain) -> tuple[float, float, float]:
    """(espérance, probabilité de gain > 0, CVaR 5 % des pertes) d'une fonction gain(cours)."""
    valeurs = sorted((gain(x), w) for x, w in scenarios)
    esp = sum(v * w for v, w in valeurs)
    p_gain = sum(w for v, w in valeurs if v > 0)
    queue, cumul = 0.0, 0.0
    for v, w in valeurs:
        if cumul >= 0.05:
            break
        prise = min(w, 0.05 - cumul)
        queue += v * prise
        cumul += prise
    return esp, p_gain, queue / 0.05 if cumul > 0 else 0.0
