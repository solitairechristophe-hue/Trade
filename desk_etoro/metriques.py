"""Critères calculés à partir des performances (série de rendements périodiques, en fractions).

Toutes les fonctions acceptent une liste de rendements (0.05 = +5 %) et le nombre de
périodes par an (12 en mensuel, 52 en hebdomadaire, 252 en quotidien). Elles renvoient
None quand la série est trop courte pour donner un chiffre qui ait un sens.
"""
from __future__ import annotations

import math
from statistics import fmean, pstdev

MIN_PERIODES = 6


def _ok(r: list[float], n: int = MIN_PERIODES) -> bool:
    return len(r) >= n


def courbe(r: list[float]) -> list[float]:
    """Valeur liquidative partant de 1."""
    v, out = 1.0, []
    for x in r:
        v *= 1 + x
        out.append(v)
    return out


def rendement_cumule(r: list[float]) -> float | None:
    return courbe(r)[-1] - 1 if r else None


def cagr(r: list[float], ppa: int) -> float | None:
    if not _ok(r, 2):
        return None
    final = courbe(r)[-1]
    if final <= 0:
        return -1.0
    return final ** (ppa / len(r)) - 1


def volatilite(r: list[float], ppa: int) -> float | None:
    if not _ok(r):
        return None
    return pstdev(r) * math.sqrt(ppa)


def sharpe(r: list[float], ppa: int, taux_sans_risque: float = 0.0) -> float | None:
    if not _ok(r):
        return None
    sigma = pstdev(r)
    if sigma == 0:
        return None
    excedent = fmean(r) - taux_sans_risque / ppa
    return excedent / sigma * math.sqrt(ppa)


def sortino(r: list[float], ppa: int, taux_sans_risque: float = 0.0) -> float | None:
    if not _ok(r):
        return None
    seuil = taux_sans_risque / ppa
    baisse = [min(0.0, x - seuil) ** 2 for x in r]
    dd = math.sqrt(sum(baisse) / len(r))
    if dd == 0:
        return None
    return (fmean(r) - seuil) / dd * math.sqrt(ppa)


def drawdown_max(r: list[float]) -> float | None:
    """Pire recul depuis un plus haut, en fraction négative (−0.25 = −25 %)."""
    if not r:
        return None
    pic, pire = 1.0, 0.0
    for v in courbe(r):
        pic = max(pic, v)
        pire = min(pire, v / pic - 1)
    return pire


def ulcer(r: list[float]) -> float | None:
    """Ulcer index : moyenne quadratique des reculs depuis le plus haut (fraction)."""
    if not _ok(r):
        return None
    pic, carres = 1.0, []
    for v in courbe(r):
        pic = max(pic, v)
        carres.append((v / pic - 1) ** 2)
    return math.sqrt(fmean(carres))


def calmar(r: list[float], ppa: int) -> float | None:
    c, dd = cagr(r, ppa), drawdown_max(r)
    if c is None or dd is None or not _ok(r):
        return None
    if dd == 0:
        return None
    return c / abs(dd)


def part_positive(r: list[float]) -> float | None:
    if not _ok(r, 3):
        return None
    return sum(1 for x in r if x > 0) / len(r)


def asymetrie(r: list[float]) -> float | None:
    if not _ok(r):
        return None
    m, s = fmean(r), pstdev(r)
    if s == 0:
        return None
    return fmean([((x - m) / s) ** 3 for x in r])


def stabilite(r: list[float]) -> float | None:
    """R² de la régression du log de la valeur liquidative sur le temps (1 = progression régulière)."""
    if not _ok(r):
        return None
    v = courbe(r)
    if min(v) <= 0:
        return 0.0
    y = [math.log(x) for x in v]
    t = list(range(len(y)))
    mt, my = fmean(t), fmean(y)
    stt = sum((a - mt) ** 2 for a in t)
    syy = sum((b - my) ** 2 for b in y)
    if stt == 0 or syy == 0:
        return None
    sty = sum((a - mt) * (b - my) for a, b in zip(t, y))
    pente = sty / stt
    if pente <= 0:
        return 0.0  # une baisse régulière n'est pas une qualité
    return sty * sty / (stt * syy)


def pire_periode(r: list[float]) -> float | None:
    return min(r) if r else None


def toutes(r: list[float], ppa: int, taux_sans_risque: float = 0.0) -> dict[str, float | None]:
    """Jeu complet de critères calculés, nommés comme dans le rapport."""
    return {
        "nb_periodes": float(len(r)),
        "rendement_cumule": rendement_cumule(r),
        "cagr": cagr(r, ppa),
        "volatilite": volatilite(r, ppa),
        "sharpe": sharpe(r, ppa, taux_sans_risque),
        "sortino": sortino(r, ppa, taux_sans_risque),
        "calmar": calmar(r, ppa),
        "drawdown_max": drawdown_max(r),
        "ulcer": ulcer(r),
        "part_periodes_positives": part_positive(r),
        "asymetrie": asymetrie(r),
        "stabilite": stabilite(r),
        "pire_periode": pire_periode(r),
    }


def rang_percentile(valeurs: dict[str, float | None], plus_haut_mieux: bool = True) -> dict[str, float]:
    """Rang centile (0 à 1, ex aequo moyennés) des valeurs connues ; les absents n'ont pas de rang."""
    connus = [(k, v) for k, v in valeurs.items() if v is not None and not math.isnan(v)]
    if not connus:
        return {}
    if len(connus) == 1:
        return {connus[0][0]: 0.5}
    connus.sort(key=lambda kv: kv[1], reverse=not plus_haut_mieux)
    rangs: dict[str, float] = {}
    i, n = 0, len(connus)
    while i < n:
        j = i
        while j + 1 < n and connus[j + 1][1] == connus[i][1]:
            j += 1
        rang = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            rangs[connus[k][0]] = rang
        i = j + 1
    return rangs
