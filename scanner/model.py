"""Modèle de données normalisé : ce que les flux Unusual Whales apportent au scoring.

Chaque flux UW est ramené à une petite structure ; la source (REST ou connecteur MCP)
n'a pas d'importance pour le reste du scanner.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlowAlert:
    """Une alerte de flux (/api/option-trades/flow-alerts)."""
    ticker: str
    type: str  # call | put
    premium: float
    size: int
    volume: int
    open_interest: int
    ask_side_premium: float
    bid_side_premium: float
    strike: float
    expiry: dt.date
    underlying_price: float
    rule: str
    has_sweep: bool = False
    has_floor: bool = False
    all_opening: bool = False
    multileg: bool = False
    created_at: dt.datetime | None = None
    sector: str = ""
    issue_type: str = ""
    marketcap: float = 0.0
    next_earnings: dt.date | None = None
    iv: float = 0.0
    delta: float = 0.0

    @property
    def bullish(self) -> bool:
        """Call acheté (ask) ou put vendu (bid) = haussier."""
        ask = self.ask_side_premium >= self.bid_side_premium
        return (self.type == "call") == ask

    @property
    def dte(self) -> int:
        base = self.created_at.date() if self.created_at else dt.date.today()
        return (self.expiry - base).days


@dataclass(frozen=True)
class DarkPoolPrint:
    ticker: str
    price: float
    size: int
    premium: float
    executed_at: dt.datetime | None = None


@dataclass(frozen=True)
class OIChange:
    ticker: str
    type: str  # call | put
    strike: float
    expiry: dt.date
    oi_change: int
    oi_before: int
    premium_change: float = 0.0
    underlying_price: float = 0.0


@dataclass(frozen=True)
class InsiderTx:
    ticker: str
    is_buy: bool
    value: float
    date: dt.date
    title: str = ""


@dataclass(frozen=True)
class CongressTx:
    ticker: str
    is_buy: bool
    amount_min: float
    date: dt.date
    member: str = ""


@dataclass(frozen=True)
class ScreenerHit:
    ticker: str
    preset: str  # Unusually Bullish | Unusually Bearish | ...
    bullish: bool
    premium: float = 0.0
    underlying_price: float = 0.0


@dataclass(frozen=True)
class OptionQuote:
    """Un contrat de la chaîne, avec cotation (bid/ask) et grecs."""
    symbol: str  # OCC, ex. SMCI261030C00039000
    type: str  # call | put
    strike: float
    expiry: dt.date
    bid: float
    ask: float
    delta: float
    open_interest: int = 0
    volume: int = 0
    iv: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class TickerContext:
    """Enrichissement par titre (un appel par flux UW)."""
    ticker: str
    price: float = 0.0
    atr14: float = 0.0
    sma20: float = 0.0
    sma50: float = 0.0
    avg_volume: float = 0.0
    options_volume: float = 0.0  # contrats du jour (calls + puts)
    stock_volume: float = 0.0  # actions du jour
    sector: str = ""
    marketcap: float = 0.0
    next_earnings: dt.date | None = None
    iv_rank: float | None = None  # 0..1
    iv30: float | None = None
    call_wall: float | None = None  # GEX : résistance (gamma call max)
    put_wall: float | None = None  # GEX : support (gamma put max)
    gex_net: float | None = None  # exposition gamma nette des dealers
    net_call_premium: float = 0.0  # flux grec du jour (net premium)
    net_put_premium: float = 0.0
    short_interest_pct: float | None = None  # part du flottant
    days_to_cover: float | None = None
    max_pain: float | None = None
    analyst_upgrades: int = 0
    analyst_downgrades: int = 0
    insider_buy_value_30d: float = 0.0
    insider_sell_value_30d: float = 0.0
    congress_buys_60d: int = 0
    congress_sells_60d: int = 0
    dark_pool_premium_1d: float = 0.0
    dark_pool_share: float | None = None  # part du volume du jour en dark pool
    oi_change_call_prem: float = 0.0
    oi_change_put_prem: float = 0.0
    institutional_ownership_pct: float | None = None
    seasonality_month_avg: float | None = None  # rendement moyen du mois en cours
    seasonality_win_rate: float | None = None
    chain: list[OptionQuote] = field(default_factory=list)
    feeds_ok: list[str] = field(default_factory=list)
    feeds_failed: list[str] = field(default_factory=list)


@dataclass
class Regime:
    """Régime de marché déduit des flux globaux (tide, GEX SPY, secteurs, calendrier)."""
    bias: float = 0.0  # -1 (baissier) .. +1 (haussier)
    risk_off: bool = False
    notes: list[str] = field(default_factory=list)
    sector_bias: dict[str, float] = field(default_factory=dict)
    spy_gex_positive: bool | None = None
    events_soon: list[str] = field(default_factory=list)
