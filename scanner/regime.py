"""Régime de marché : agrégation des flux globaux Unusual Whales (fonctions pures)."""
from __future__ import annotations

import datetime as dt
import math

from .model import Regime


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def tide_bias(points: list[dict], window: int = 12) -> float:
    """Biais -1..+1 d'après la pente récente du market tide (net call vs net put premium).

    `points` : lignes {"net_call_premium", "net_put_premium"} ordonnées dans le temps
    (5 minutes par ligne : window=12 → dernière heure).
    """
    if len(points) < 2:
        return 0.0
    recent = points[-window:] if len(points) > window else points
    d_call = _f(recent[-1].get("net_call_premium")) - _f(recent[0].get("net_call_premium"))
    d_put = _f(recent[-1].get("net_put_premium")) - _f(recent[0].get("net_put_premium"))
    # calls achetés et puts vendus = haussier ; échelle ~50 M$ sur l'heure
    return math.tanh((d_call - d_put) / 50_000_000)


def level_bias(points: list[dict]) -> float:
    """Biais du niveau absolu du jour (cumul net call − net put), -1..+1."""
    if not points:
        return 0.0
    last = points[-1]
    return math.tanh((_f(last.get("net_call_premium")) - _f(last.get("net_put_premium"))) / 150_000_000)


def sector_biases(sector_points: dict[str, list[dict]]) -> dict[str, float]:
    return {s: round(0.5 * tide_bias(p) + 0.5 * level_bias(p), 3) for s, p in sector_points.items() if p}


EVENEMENTS_MAJEURS = ("fomc", "fed ", "federal reserve", "rate decision", "interest rate", "powell", "cpi",
                      "consumer price", "pce", "nonfarm", "non-farm", "payroll", "employment report", "jobs report",
                      "gdp", "ppi", "producer price", "ism ", "retail sales", "jobless claims")


def evenement_majeur(e: dict) -> bool:
    imp = str(e.get("importance") or e.get("impact") or "").lower()
    if imp in ("high", "3", "major"):
        return True
    nom = str(e.get("event") or e.get("name") or e.get("title") or "").lower()
    return any(k in nom for k in EVENEMENTS_MAJEURS)


def events_within(events: list[dict], now: dt.datetime, hours: float = 2.0) -> list[str]:
    """Événements macro majeurs (FOMC, CPI, NFP, PIB…) à venir dans les prochaines heures."""
    out = []
    for e in events:
        if not evenement_majeur(e):
            continue
        t = e.get("time") or e.get("datetime") or e.get("date")
        if not t:
            continue
        try:
            when = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        delta = (when - now.astimezone(dt.timezone.utc)).total_seconds() / 3600
        if 0 <= delta <= hours:
            out.append(str(e.get("event") or e.get("name") or e.get("title") or "événement"))
    return out


def build_regime(tide: list[dict], sector_tides: dict[str, list[dict]], spy_gex_net: float | None,
                 events: list[dict], now: dt.datetime, market_closed: bool = False) -> Regime:
    r = Regime()
    tb, lb = tide_bias(tide), level_bias(tide)
    r.bias = max(-1.0, min(1.0, 0.6 * tb + 0.4 * lb))
    r.notes.append(f"Market tide : pente 1 h {tb:+.2f}, niveau du jour {lb:+.2f}")
    r.sector_bias = sector_biases(sector_tides)
    if spy_gex_net is not None:
        r.spy_gex_positive = spy_gex_net > 0
        r.notes.append("SPY en gamma " + ("positif (régime calme, retour à la moyenne)" if r.spy_gex_positive
                                          else "négatif (régime nerveux, mouvements amplifiés)"))
    r.events_soon = events_within(events, now)
    if r.events_soon:
        r.risk_off = True
        r.notes.append("Événement macro imminent : " + ", ".join(r.events_soon[:3]))
    if market_closed:
        r.notes.append("Marché fermé : scan sur données de la veille")
    return r
