"""Choix de la structure d'options et des niveaux (fonctions pures sur la chaîne cotée).

Débit (défaut) : vertical acheté, jambe longue ~delta 0,50, jambe courte ~delta 0,25
(ou au mur gamma s'il est dans la fourchette). Crédit (IV rank élevé) : vertical vendu,
jambe courte ~delta 0,25, jambe longue plus loin. Les jambes sont toujours décrites dans
le sens débit, comme l'exige le robot ; un crédit est la vente (side SELL) de ce combo.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from .model import OptionQuote, TickerContext


@dataclass(frozen=True)
class Proposition:
    symbol: str
    direction: str  # up | down
    side: str  # BUY (débit) | SELL (crédit)
    strategy: str  # ex. "bull call spread"
    legs: tuple[dict, ...]
    expiry: dt.date
    width: float
    limit_price: float
    price_cap: float
    take_profit: float
    stop_loss: float
    premium_per_contract: float  # $ par combo : débit payé ou marge bloquée
    max_loss_per_contract: float  # $ par combo : perte si le SL est exécuté (avec marge de glissement)
    max_gain_per_contract: float  # $ par combo si le TP est exécuté
    condition: dict | None
    underlying_stop: float
    time_exit: dt.date
    note: str


def _arrondi(p: float) -> float:
    """Pas de cotation des options : 0,01 sous 3 $, 0,05 au-dessus."""
    pas = 0.01 if p < 3 else 0.05
    return round(math.floor(p / pas + 1e-9) * pas, 2)


def _arrondi_haut(p: float) -> float:
    pas = 0.01 if p < 3 else 0.05
    return round(math.ceil(p / pas - 1e-9) * pas, 2)


def expiries_valides(chain: list[OptionQuote], today: dt.date, min_dte: int, max_dte: int,
                     next_earnings: dt.date | None) -> list[dt.date]:
    """Échéances dans la fenêtre, en évitant celles qui enjambent les résultats."""
    exps = sorted({q.expiry for q in chain})
    ok = []
    for e in exps:
        dte = (e - today).days
        if not min_dte <= dte <= max_dte:
            continue
        if next_earnings and today <= next_earnings <= e:
            continue
        ok.append(e)
    if not ok and next_earnings:  # repli : une échéance avant les résultats, ≥ 10 jours
        ok = [e for e in exps if 10 <= (e - today).days <= max_dte and e < next_earnings]
    return ok


def _par_delta(quotes: list[OptionQuote], cible: float) -> OptionQuote | None:
    cotes = [q for q in quotes if q.bid > 0 and q.ask > 0 and q.ask >= q.bid]
    if not cotes:
        return None
    return min(cotes, key=lambda q: abs(abs(q.delta) - cible))


def _liquide(q: OptionQuote) -> bool:
    return q.ask > 0 and q.spread <= max(0.10, 0.15 * q.mid) and (q.open_interest >= 50 or q.volume >= 50)


def proposer(ctx: TickerContext, direction: str, today: dt.date, *, min_dte: int, max_dte: int,
             long_delta: float = 0.50, short_delta: float = 0.25, iv_rank_credit: float = 0.55,
             tp_fraction: float = 0.55, sl_fraction: float = 0.50, max_premium: float = 1e9
             ) -> Proposition | None:
    """Construit la proposition pour le titre, ou None si aucune structure propre n'est possible."""
    if not ctx.chain or not ctx.price:
        return None
    credit = ctx.iv_rank is not None and ctx.iv_rank >= iv_rank_credit
    atr = ctx.atr14 or ctx.price * 0.02
    for expiry in expiries_valides(ctx.chain, today, min_dte, max_dte, ctx.next_earnings):
        right = "call" if (direction == "up") != credit else "put"
        quotes = [q for q in ctx.chain if q.expiry == expiry and q.type == right]
        p = _vertical_credit(ctx, direction, expiry, quotes, today, short_delta, atr, max_premium) if credit \
            else _vertical_debit(ctx, direction, expiry, quotes, today, long_delta, short_delta, atr,
                                 tp_fraction, sl_fraction, max_premium)
        if p:
            return p
    return None


def _condition_et_stop(ctx: TickerContext, direction: str, atr: float) -> tuple[dict, float]:
    if direction == "up":
        cond = {"op": ">=", "price": round(ctx.price + 0.15 * atr, 2)}
        stop = ctx.price - 1.5 * atr
        if ctx.put_wall and ctx.price - 2.5 * atr < ctx.put_wall < ctx.price - 0.5 * atr:
            stop = ctx.put_wall - 0.1 * atr  # juste sous le support gamma
    else:
        cond = {"op": "<=", "price": round(ctx.price - 0.15 * atr, 2)}
        stop = ctx.price + 1.5 * atr
        if ctx.call_wall and ctx.price + 0.5 * atr < ctx.call_wall < ctx.price + 2.5 * atr:
            stop = ctx.call_wall + 0.1 * atr
    return cond, round(stop, 2)


def _vertical_debit(ctx, direction, expiry, quotes, today, long_delta, short_delta, atr,
                    tp_fraction, sl_fraction, max_premium) -> Proposition | None:
    longue = _par_delta(quotes, long_delta)
    if longue is None or not _liquide(longue):
        return None
    # jambe courte : delta cible, ou le mur gamma s'il tombe entre 0,8 et 2,5 ATR
    cible = _par_delta(quotes, short_delta)
    mur = ctx.call_wall if direction == "up" else ctx.put_wall
    if mur and 0.8 * atr <= abs(mur - ctx.price) <= 2.5 * atr:
        proches = [q for q in quotes if (q.strike >= mur if direction == "up" else q.strike <= mur)]
        if proches:
            cible = min(proches, key=lambda q: abs(q.strike - mur))
    if cible is None or not _liquide(cible) or cible.strike == longue.strike:
        return None
    if (direction == "up" and cible.strike < longue.strike) or (direction == "down" and cible.strike > longue.strike):
        return None
    width = abs(cible.strike - longue.strike)
    mid = longue.mid - cible.mid
    if mid <= 0.05 or mid >= 0.8 * width:
        return None  # trop cher pour le gain possible
    limit = _arrondi_haut(mid + 0.15 * (longue.spread + cible.spread) / 2)
    if limit * 100 > max_premium:
        return None
    cap = _arrondi_haut(limit * 1.07)
    tp = _arrondi(limit + tp_fraction * (width - limit))
    sl = _arrondi(limit * (1 - sl_fraction))
    if not sl < limit < tp:
        return None
    cond, stop = _condition_et_stop(ctx, direction, atr)
    strat = "bull call spread" if direction == "up" else "bear put spread"
    legs = (
        {"expiry": expiry.strftime("%Y%m%d"), "strike": longue.strike, "right": "C" if direction == "up" else "P",
         "action": "BUY", "ratio": 1},
        {"expiry": expiry.strftime("%Y%m%d"), "strike": cible.strike, "right": "C" if direction == "up" else "P",
         "action": "SELL", "ratio": 1},
    )
    return Proposition(
        symbol=ctx.ticker, direction=direction, side="BUY", strategy=strat, legs=legs, expiry=expiry,
        width=width, limit_price=limit, price_cap=cap, take_profit=tp, stop_loss=sl,
        premium_per_contract=round(limit * 100, 2),
        max_loss_per_contract=round((limit - sl) * 100 * 1.10, 2),
        max_gain_per_contract=round((tp - limit) * 100, 2),
        condition=cond, underlying_stop=stop, time_exit=expiry - dt.timedelta(days=7),
        note=f"{strat} {longue.strike}/{cible.strike} {expiry.isoformat()} (débit, mid {mid:.2f})",
    )


def _vertical_credit(ctx, direction, expiry, quotes, today, short_delta, atr, max_premium) -> Proposition | None:
    """Bull put spread (up) ou bear call spread (down) : on vend le combo décrit en sens débit."""
    courte = _par_delta(quotes, short_delta)
    if courte is None or not _liquide(courte):
        return None
    plus_loin = [q for q in quotes if (q.strike < courte.strike if direction == "up" else q.strike > courte.strike)]
    plus_loin = [q for q in plus_loin if abs(q.strike - courte.strike) <= 2 * atr and _liquide(q)]
    if not plus_loin:
        return None
    longue = max(plus_loin, key=lambda q: abs(q.strike - courte.strike))
    width = abs(courte.strike - longue.strike)
    credit_mid = courte.mid - longue.mid
    if credit_mid < 0.2 * width or credit_mid <= 0.05:
        return None  # pas assez payé pour le risque
    limit = _arrondi(credit_mid - 0.15 * (courte.spread + longue.spread) / 2)
    marge = (width - limit) * 100
    if marge > max_premium:
        return None
    tp = _arrondi(limit * 0.5)
    sl = _arrondi_haut(limit * 2.0)
    if not tp < limit < sl:
        return None
    cond, stop = _condition_et_stop(ctx, direction, atr)
    right = "P" if direction == "up" else "C"
    strat = "bull put spread" if direction == "up" else "bear call spread"
    # sens débit du combo : on achète la jambe chère (la courte du crédit), on vend la lointaine
    legs = (
        {"expiry": expiry.strftime("%Y%m%d"), "strike": courte.strike, "right": right, "action": "BUY", "ratio": 1},
        {"expiry": expiry.strftime("%Y%m%d"), "strike": longue.strike, "right": right, "action": "SELL", "ratio": 1},
    )
    return Proposition(
        symbol=ctx.ticker, direction=direction, side="SELL", strategy=strat, legs=legs, expiry=expiry,
        width=width, limit_price=limit, price_cap=limit, take_profit=tp, stop_loss=sl,
        premium_per_contract=round(marge, 2),
        max_loss_per_contract=round((sl - limit) * 100 * 1.10, 2),
        max_gain_per_contract=round((limit - tp) * 100, 2),
        condition=cond, underlying_stop=stop, time_exit=expiry - dt.timedelta(days=7),
        note=f"{strat} {courte.strike}/{longue.strike} {expiry.isoformat()} (crédit, mid {credit_mid:.2f})",
    )
