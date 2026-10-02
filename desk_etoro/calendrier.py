"""Calendrier de la revue hebdomadaire : première séance NYSE de chaque semaine, à l'ouverture (9 h 30, New York)."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OUVERTURE = dt.time(9, 30)


def _paques(annee: int) -> dt.date:
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(annee, mois, jour)


def _nieme(annee: int, mois: int, jour_semaine: int, n: int) -> dt.date:
    d = dt.date(annee, mois, 1)
    d += dt.timedelta(days=(jour_semaine - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _dernier(annee: int, mois: int, jour_semaine: int) -> dt.date:
    d = dt.date(annee + (mois == 12), mois % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - jour_semaine) % 7)


def _observe(d: dt.date) -> dt.date:
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def feries(annee: int) -> frozenset[dt.date]:
    j = {
        _nieme(annee, 1, 0, 3),  # Martin Luther King
        _nieme(annee, 2, 0, 3),  # Presidents' Day
        _paques(annee) - dt.timedelta(days=2),  # Vendredi saint
        _dernier(annee, 5, 0),  # Memorial Day
        _observe(dt.date(annee, 7, 4)),
        _nieme(annee, 9, 0, 1),  # Labor Day
        _nieme(annee, 11, 3, 4),  # Thanksgiving
        _observe(dt.date(annee, 12, 25)),
    }
    nouvel_an = dt.date(annee, 1, 1)
    if nouvel_an.weekday() != 5:  # un 1er janvier un samedi n'est pas rattrapé le vendredi
        j.add(_observe(nouvel_an))
    if annee >= 2022:
        j.add(_observe(dt.date(annee, 6, 19)))  # Juneteenth
    return frozenset(j)


def est_seance(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in feries(d.year)


def premiere_seance_semaine(d: dt.date) -> dt.date | None:
    lundi = d - dt.timedelta(days=d.weekday())
    for k in range(5):
        j = lundi + dt.timedelta(days=k)
        if est_seance(j):
            return j
    return None


def est_jour_de_revue(d: dt.date) -> bool:
    return premiere_seance_semaine(d) == d


def prochaine_revue(maintenant: dt.datetime) -> dt.datetime:
    """Prochaine ouverture de première séance de semaine, à partir de `maintenant` (inclus)."""
    m = maintenant.astimezone(NY)
    d = m.date()
    for _ in range(60):
        j = premiere_seance_semaine(d)
        if j is not None:
            ouverture = dt.datetime.combine(j, OUVERTURE, NY)
            if ouverture >= m:
                return ouverture
        d = d - dt.timedelta(days=d.weekday()) + dt.timedelta(weeks=1)
    raise RuntimeError("aucune séance trouvée")  # pragma: no cover
