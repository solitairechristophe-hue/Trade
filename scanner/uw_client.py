"""Client de l'API REST publique Unusual Whales (https://api.unusualwhales.com/docs).

Chaque méthode ramène un flux à son modèle normalisé (scanner.model). Les champs des réponses
sont lus de façon tolérante (`_g`) : un champ absent donne 0 / None, jamais une exception.
Le token (UW_TOKEN) ne sort jamais de ce module.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from typing import Any

import requests

from .config import ScanConfig
from .model import (CongressTx, DarkPoolPrint, FlowAlert, InsiderTx, OIChange, OptionQuote,
                    ScreenerHit, TickerContext)

log = logging.getLogger("scanner")
OCC = re.compile(r"^(?P<symbol>[A-Z.\-]+)(?P<expiry>\d{6})(?P<type>[PC])(?P<strike>\d{8})$")
SECTEURS = ("Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy",
            "Financial Services", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities")


def _g(d: dict, *cles: str, defaut=None):
    for c in cles:
        if c in d and d[c] is not None:
            return d[c]
    return defaut


def _f(x, defaut: float = 0.0) -> float:
    try:
        v = float(x)
        return defaut if v != v else v
    except (TypeError, ValueError):
        return defaut


def _i(x, defaut: int = 0) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return defaut


def _date(x) -> dt.date | None:
    if not x:
        return None
    try:
        return dt.date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _datetime(x) -> dt.datetime | None:
    if x in (None, ""):
        return None
    try:
        if isinstance(x, (int, float)):
            return dt.datetime.fromtimestamp(x / (1000 if x > 1e11 else 1), tz=dt.timezone.utc)
        return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None


def occ(symbole: str) -> tuple[str, dt.date, str, float] | None:
    m = OCC.match(symbole or "")
    if not m:
        return None
    return (m["symbol"], dt.datetime.strptime(m["expiry"], "%y%m%d").date(),
            "call" if m["type"] == "C" else "put", int(m["strike"]) / 1000)


class UwClient:
    def __init__(self, cfg: ScanConfig, session: requests.Session | None = None):
        self.cfg = cfg
        self.s = session or requests.Session()
        self.s.headers.update({"Accept": "application/json, text/plain",
                               "Authorization": f"Bearer {cfg.uw_token}"})
        self.appels = 0

    # --- transport ------------------------------------------------------------------
    def get(self, chemin: str, params: dict | None = None, cle: str | None = "data") -> Any:
        """GET avec 3 essais (429/5xx, Retry-After respecté). Renvoie le contenu de `cle` (ou tout le JSON)."""
        url = f"{self.cfg.uw_base_url}{chemin}"
        p = {k: v for k, v in (params or {}).items() if v is not None}
        for essai in range(3):
            self.appels += 1
            r = self.s.get(url, params=p, timeout=self.cfg.uw_timeout)
            if r.status_code in (429, 503, 502, 504) and essai < 2:
                time.sleep(float(r.headers.get("Retry-After", 2 * (essai + 1))))
                continue
            r.raise_for_status()
            doc = r.json()
            if cle is None or not isinstance(doc, dict):
                return doc
            return doc.get(cle, doc if cle not in doc else [])
        raise RuntimeError(f"{chemin} : trop de tentatives")

    def _liste(self, chemin: str, params: dict | None = None, cle: str = "data") -> list[dict]:
        v = self.get(chemin, params, cle)
        return v if isinstance(v, list) else []

    # --- flux de marché -------------------------------------------------------------
    def market_tide(self) -> list[dict]:
        return self._liste("/api/market/market-tide", {"interval_5m": "true"})

    def sector_tides(self) -> dict[str, list[dict]]:
        out = {}
        for s in SECTEURS:
            try:
                out[s] = self._liste(f"/api/market/{s}/sector-tide")
            except Exception as e:
                log.warning("sector tide %s : %s", s, e)
        return out

    def economic_calendar(self) -> list[dict]:
        return self._liste("/api/market/economic-calendar")

    def spy_gex_net(self) -> float | None:
        rows = self._liste("/api/stock/SPY/greek-exposure", {"timeframe": "1W"})
        if not rows:
            return None
        last = max(rows, key=lambda r: str(_g(r, "date", defaut="")))
        return _f(_g(last, "call_gamma")) + _f(_g(last, "put_gamma"))

    def top_net_impact(self) -> list[dict]:
        return self._liste("/api/market/top-net-impact", {"limit": 50, "issue_types[]": ["Common Stock", "ADR", "ETF"]})

    # --- flux de candidats ----------------------------------------------------------
    def flow_alerts(self, newer_than: dt.datetime, older_than: dt.datetime | None = None,
                    limit: int = 200) -> list[FlowAlert]:
        rows = self._liste("/api/option-trades/flow-alerts", {
            "newer_than": newer_than.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
            "older_than": older_than.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if older_than else None,
            "order": "premium" if older_than else None,
            "min_premium": int(self.cfg.min_premium_alert), "min_dte": 5, "max_dte": 90,
            "issue_types[]": list(self.cfg.issue_types), "limit": limit,
        })
        out = []
        for r in rows:
            exp = _date(_g(r, "expiry"))
            if not exp:
                continue
            out.append(FlowAlert(
                ticker=str(_g(r, "ticker", defaut="")).upper(), type=str(_g(r, "type", defaut="call")).lower(),
                premium=_f(_g(r, "total_premium", "premium")), size=_i(_g(r, "total_size", "size")),
                volume=_i(_g(r, "volume")), open_interest=_i(_g(r, "open_interest")),
                ask_side_premium=_f(_g(r, "total_ask_side_prem")), bid_side_premium=_f(_g(r, "total_bid_side_prem")),
                strike=_f(_g(r, "strike")), expiry=exp, underlying_price=_f(_g(r, "underlying_price")),
                rule=str(_g(r, "alert_rule", "rule_name", defaut="")), has_sweep=bool(_g(r, "has_sweep", defaut=False)),
                has_floor=bool(_g(r, "has_floor", defaut=False)), all_opening=bool(_g(r, "all_opening_trades", defaut=False)),
                multileg=bool(_g(r, "has_multileg", defaut=False)), created_at=_datetime(_g(r, "created_at", "start_time")),
                sector=str(_g(r, "sector", defaut="") or ""), issue_type=str(_g(r, "issue_type", defaut="") or ""),
                marketcap=_f(_g(r, "marketcap")), next_earnings=_date(_g(r, "next_earnings_date")),
                iv=_f(_g(r, "iv")), delta=_f(_g(r, "delta")),
            ))
        return out

    def screener_hits(self) -> list[ScreenerHit]:
        """Hottest chains : contrats inhabituels côté ask (calls = haussier, puts = baissier)."""
        out = []
        for typ, bullish, preset in (("call", True, "Unusually Bullish"), ("put", False, "Unusually Bearish")):
            rows = self._liste("/api/screener/option-contracts", {
                "type": typ, "vol_greater_oi": "true", "is_otm": "true", "min_premium": int(self.cfg.min_premium_alert * 2),
                "min_ask_perc": "0.6", "min_dte": 7, "max_dte": 60, "issue_types[]": list(self.cfg.issue_types),
                "order": "premium", "order_direction": "desc", "limit": 40,
            })
            for r in rows:
                tk = _g(r, "ticker", "underlying_symbol", "symbol")
                if not tk:
                    o = occ(str(_g(r, "option_symbol", "option_chain", defaut="")))
                    tk = o[0] if o else None
                if tk:
                    out.append(ScreenerHit(ticker=str(tk).upper(), preset=preset, bullish=bullish,
                                           premium=_f(_g(r, "premium", "total_premium")),
                                           underlying_price=_f(_g(r, "underlying_price", "stock_price"))))
        return out

    def dark_pool_recent(self) -> list[DarkPoolPrint]:
        rows = self._liste("/api/darkpool/recent", {"min_premium": 5_000_000, "limit": 200, "order_by": "premium"})
        return [DarkPoolPrint(ticker=str(_g(r, "ticker", defaut="")).upper(), price=_f(_g(r, "price")),
                              size=_i(_g(r, "size")), premium=_f(_g(r, "premium")),
                              executed_at=_datetime(_g(r, "executed_at"))) for r in rows if _g(r, "ticker")]

    def market_oi_changes(self) -> list[OIChange]:
        rows = self._liste("/api/market/oi-change", {"limit": 100, "order": "desc"})
        return [o for o in (self._oi_change(r) for r in rows) if o]

    def _oi_change(self, r: dict) -> OIChange | None:
        o = occ(str(_g(r, "option_symbol", "option_chain", defaut="")))
        if not o:
            return None
        tk, exp, typ, strike = o
        chg = _i(_g(r, "oi_change", "oi_diff"))
        prem = _f(_g(r, "premium_change", "oi_change_premium"))
        if not prem:
            prem = chg * _f(_g(r, "avg_price", "last_price", "price")) * 100
        return OIChange(ticker=tk, type=typ, strike=strike, expiry=exp, oi_change=chg,
                        oi_before=_i(_g(r, "prev_oi", "last_oi", "previous_oi")), premium_change=prem,
                        underlying_price=_f(_g(r, "underlying_price")))

    def insider_recent(self, jours: int = 14) -> list[InsiderTx]:
        depuis = (dt.date.today() - dt.timedelta(days=jours)).isoformat()
        rows = self._liste("/api/insider/transactions", {
            "transaction_codes[]": ["P", "S"], "start_date": depuis, "min_value": 200_000,
            "common_stock_only": "true", "limit": 300,
        })
        out = []
        for r in rows:
            code = str(_g(r, "transaction_code", "code", defaut="")).upper()
            val = _f(_g(r, "value", "amount"))
            if not val:
                val = _f(_g(r, "shares", "amount")) * _f(_g(r, "price"))
            out.append(InsiderTx(ticker=str(_g(r, "ticker", defaut="")).upper(), is_buy=code == "P", value=abs(val),
                                 date=_date(_g(r, "transaction_date", "filing_date")) or dt.date.today(),
                                 title=str(_g(r, "title", "owner_name", defaut="") or "")))
        return [i for i in out if i.ticker]

    def congress_recent(self) -> list[CongressTx]:
        rows = self._liste("/api/congress/recent-trades", {"limit": 200})
        out = []
        for r in rows:
            typ = str(_g(r, "txn_type", "transaction_type", "type", defaut="")).lower()
            if "purchase" not in typ and "buy" not in typ and "sale" not in typ and "sell" not in typ:
                continue
            amt = _g(r, "amounts", "amount", defaut="")
            m = re.search(r"[\d,]+", str(amt))
            out.append(CongressTx(ticker=str(_g(r, "ticker", defaut="")).upper(), is_buy="purchase" in typ or "buy" in typ,
                                  amount_min=_f(m.group(0).replace(",", "")) if m else 0.0,
                                  date=_date(_g(r, "transaction_date", "filed_at_date")) or dt.date.today(),
                                  member=str(_g(r, "reporter", "member", "name", defaut="") or "")))
        return [c for c in out if c.ticker]

    # --- enrichissement par titre ---------------------------------------------------
    def enrich(self, ticker: str, today: dt.date, min_dte: int, max_dte: int) -> TickerContext:
        ctx = TickerContext(ticker=ticker)

        def essai(nom: str, fn):
            try:
                fn()
                ctx.feeds_ok.append(nom)
            except Exception as e:
                ctx.feeds_failed.append(f"{nom} ({e.__class__.__name__})")
                log.info("%s %s : %s", ticker, nom, e)

        def screener():
            rows = self._liste("/api/screener/stocks", {"ticker": ticker, "limit": 1})
            if rows:
                r = rows[0]
                ctx.price = _f(_g(r, "price"))
                ctx.atr14 = _f(_g(r, "atr_14"))
                ctx.sma20 = _f(_g(r, "ema_20"))
                ctx.marketcap = _f(_g(r, "marketcap"))
                if _g(r, "iv_rank") is not None:
                    v = _f(_g(r, "iv_rank"))
                    ctx.iv_rank = v / 100 if v > 1 else v  # fraction ou pourcentage selon la version
                ctx.iv30 = _f(_g(r, "iv30d")) or None
                ctx.net_call_premium = _f(_g(r, "net_call_premium"))
                ctx.net_put_premium = _f(_g(r, "net_put_premium"))
                ctx.avg_volume = _f(_g(r, "avg30_volume", "avg_30_day_volume", "stock_volume"))
                ctx.options_volume = _f(_g(r, "call_volume")) + _f(_g(r, "put_volume"))
                ctx.stock_volume = _f(_g(r, "stock_volume"))
                ctx.sector = str(_g(r, "sector", defaut="") or "")
                ctx.next_earnings = _date(_g(r, "next_earnings_date", "earnings_date"))
                ctx.insider_buy_value_30d = _f(_g(r, "insider_buy_volume3m")) * ctx.price if _g(r, "insider_buy_volume3m") else 0.0
                ctx.insider_sell_value_30d = _f(_g(r, "insider_sell_volume3m")) * ctx.price if _g(r, "insider_sell_volume3m") else 0.0

        def info():
            r = self.get(f"/api/stock/{ticker}/info")
            if isinstance(r, dict):
                ctx.sector = ctx.sector or str(_g(r, "sector", defaut="") or "")
                ctx.marketcap = ctx.marketcap or _f(_g(r, "marketcap", "market_cap"))
                ctx.next_earnings = ctx.next_earnings or _date(_g(r, "next_earnings_date", "earnings_date"))

        def candles():
            rows = self._liste(f"/api/stock/{ticker}/ohlc/1d", {"limit": 60})
            rows = sorted(rows, key=lambda r: str(_g(r, "date", "start_time", defaut="")))
            closes = [_f(_g(r, "close")) for r in rows if _g(r, "close")]
            if closes:
                ctx.price = ctx.price or closes[-1]
                if len(closes) >= 20:
                    ctx.sma20 = ctx.sma20 or sum(closes[-20:]) / 20
                if len(closes) >= 50:
                    ctx.sma50 = sum(closes[-50:]) / 50
                trs = []
                for prev, r in zip(rows[-15:-1], rows[-14:]):
                    h, l, pc = _f(_g(r, "high")), _f(_g(r, "low")), _f(_g(prev, "close"))
                    trs.append(max(h - l, abs(h - pc), abs(l - pc)))
                if trs and not ctx.atr14:
                    ctx.atr14 = sum(trs) / len(trs)
                vols = [_f(_g(r, "volume")) for r in rows[-30:]]
                if vols:
                    ctx.avg_volume = sum(vols) / len(vols)

        def gex_levels():
            r = self.get(f"/api/stock/{ticker}/gex-levels", {"source": "vol"})
            if isinstance(r, list) and r:
                r = r[-1]
            if isinstance(r, dict):
                ctx.call_wall = _f(_g(r, "call_wall")) or None
                ctx.put_wall = _f(_g(r, "put_wall")) or None

        def gex():
            rows = self._liste(f"/api/stock/{ticker}/greek-exposure", {"timeframe": "1W"})
            if rows:
                last = max(rows, key=lambda r: str(_g(r, "date", defaut="")))
                ctx.gex_net = _f(_g(last, "call_gamma")) + _f(_g(last, "put_gamma"))

        def shorts():
            rows = self._liste(f"/api/shorts/{ticker}/interest-float/v2")
            if rows:
                last = max(rows, key=lambda r: str(_g(r, "date", "settlement_date", defaut="")))
                pct = _f(_g(last, "short_interest_pct_float", "percent_of_float", "si_pct_float"))
                if pct > 1:
                    pct /= 100
                ctx.short_interest_pct = pct or None
                ctx.days_to_cover = _f(_g(last, "days_to_cover")) or None

        def max_pain():
            rows = self._liste(f"/api/stock/{ticker}/max-pain")
            cibles = [r for r in rows if _date(_g(r, "expiry", "expiration")) and
                      min_dte <= (_date(_g(r, "expiry", "expiration")) - today).days <= max_dte]
            if cibles:
                ctx.max_pain = _f(_g(cibles[0], "max_pain", "strike")) or None

        def analysts():
            depuis = (today - dt.timedelta(days=30)).isoformat()
            rows = self._liste("/api/screener/analysts", {"ticker": ticker, "newer_than": depuis, "limit": 50})
            for r in rows:
                a = str(_g(r, "action", defaut="")).lower()
                if a == "upgraded":
                    ctx.analyst_upgrades += 1
                elif a == "downgraded":
                    ctx.analyst_downgrades += 1

        def insiders():
            r = self.get(f"/api/stock/{ticker}/insider-buy-sells")
            rows = r if isinstance(r, list) else [r] if isinstance(r, dict) else []
            if rows:
                last = rows[-1]
                ctx.insider_buy_value_30d = max(ctx.insider_buy_value_30d, _f(_g(last, "purchases_notional", "buy_notional")))
                ctx.insider_sell_value_30d = max(ctx.insider_sell_value_30d, _f(_g(last, "sells_notional", "sell_notional")))

        def dark_pool():
            rows = self._liste(f"/api/darkpool/{ticker}", {"date": today.isoformat(), "min_premium": 1_000_000, "limit": 200})
            ctx.dark_pool_premium_1d = sum(_f(_g(r, "premium")) for r in rows)

        def oi_change():
            rows = self._liste(f"/api/stock/{ticker}/oi-change", {"limit": 40, "order": "desc"})
            for r in rows:
                o = self._oi_change(r)
                if o and o.oi_change > 0:
                    if o.type == "call":
                        ctx.oi_change_call_prem += o.premium_change
                    else:
                        ctx.oi_change_put_prem += o.premium_change

        def vol_context():
            r = self.get(f"/api/stock/{ticker}/volatility/context")
            if isinstance(r, dict):
                rank = _g(r, "iv_rank", "iv30d_rank", "iv_rank_1y")
                if isinstance(rank, dict):
                    rank = _g(rank, "rank", "value")
                if rank is not None:
                    v = _f(rank)
                    ctx.iv_rank = v / 100 if v > 1 else v
                ctx.next_earnings = ctx.next_earnings or _date(_g(r, "next_earnings_date", "earnings_date"))

        def net_prem():
            rows = self._liste(f"/api/stock/{ticker}/net-prem-ticks")
            if rows and not (ctx.net_call_premium or ctx.net_put_premium):
                ctx.net_call_premium = sum(_f(_g(r, "net_call_premium")) for r in rows)
                ctx.net_put_premium = sum(_f(_g(r, "net_put_premium")) for r in rows)

        def seasonality():
            rows = self._liste(f"/api/seasonality/{ticker}/monthly")
            for r in rows:
                if _i(_g(r, "month")) == today.month:
                    avg = _f(_g(r, "avg_change", "average_change", "avg_return"))
                    ctx.seasonality_month_avg = avg / 100 if abs(avg) > 1 else avg
                    wr = _f(_g(r, "positive_months_perc", "win_rate"))
                    ctx.seasonality_win_rate = wr / 100 if wr > 1 else wr

        def chain():
            rows = self._liste(f"/api/stock/{ticker}/option-contracts", {
                "min_dte": max(min_dte - 7, 7), "max_dte": max_dte, "exclude_zero_oi_chains": "true", "limit": 500})
            for r in rows:
                o = occ(str(_g(r, "option_symbol", "option_chain", defaut="")))
                if not o:
                    continue
                _, exp, typ, strike = o
                ctx.chain.append(OptionQuote(
                    symbol=str(_g(r, "option_symbol", "option_chain")), type=typ, strike=strike, expiry=exp,
                    bid=_f(_g(r, "bid", "nbbo_bid")), ask=_f(_g(r, "ask", "nbbo_ask")), delta=_f(_g(r, "delta")),
                    open_interest=_i(_g(r, "open_interest")), volume=_i(_g(r, "volume")),
                    iv=_f(_g(r, "implied_volatility", "iv"))))

        for nom, fn in (("stock screener", screener), ("ticker info", info), ("ohlc 1d", candles),
                        ("gex levels", gex_levels), ("greek exposure", gex), ("short interest", shorts),
                        ("max pain", max_pain), ("analyst ratings", analysts), ("insider buy/sells", insiders),
                        ("dark pool ticker", dark_pool), ("oi change ticker", oi_change),
                        ("volatility context", vol_context), ("net premium ticks", net_prem),
                        ("seasonality", seasonality), ("option contracts", chain)):
            if nom == "seasonality" and not self.cfg.seasonality_feeds:
                continue
            essai(nom, fn)
        return ctx

    def daily_candles(self, ticker: str, limit: int = 120) -> list[dict]:
        """Bougies journalières triées dans le temps : {date, open, high, low, close}."""
        rows = self._liste(f"/api/stock/{ticker}/ohlc/1d", {"limit": limit})
        out = [{"date": _date(_g(r, "date", "start_time")), "open": _f(_g(r, "open")), "high": _f(_g(r, "high")),
                "low": _f(_g(r, "low")), "close": _f(_g(r, "close"))} for r in rows]
        return sorted([c for c in out if c["date"] and c["close"]], key=lambda c: c["date"])
