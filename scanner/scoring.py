"""Scoring de confluence : combine tous les flux Unusual Whales en un score 0..100 et une direction.

Fonctions pures, testées. Chaque facteur est ramené à [-1, +1] (signe = haussier/baissier,
0 = pas d'information), puis pondéré. Les facteurs « confirmation » (dark pool, short
interest…) n'ont pas de direction propre : ils renforcent la direction du flux d'options.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field

from .model import (CongressTx, DarkPoolPrint, FlowAlert, InsiderTx, OIChange, Regime,
                    ScreenerHit, TickerContext)

POIDS = {
    "flow": 3.0,          # flux d'options (ask-side calls / puts) sur la fenêtre
    "flow_quality": 1.0,  # urgence : sweeps, fills ascendants, vol > OI, ouverture
    "screener": 1.5,      # presets Unusually Bullish / Bearish, Deep Conviction
    "greek_flow": 1.5,    # net premium calls vs puts du jour (ticker)
    "oi_change": 1.0,     # variations d'intérêt ouvert (positionnement confirmé la veille)
    "dark_pool": 1.0,     # gros blocs en dark pool (confirmation)
    "insider": 1.0,       # achats/ventes d'initiés 30 j
    "congress": 0.5,      # transactions du Congrès 60 j
    "analyst": 0.5,       # relèvements/abaissements récents
    "trend": 1.5,         # prix vs SMA20/SMA50
    "gex": 1.0,           # position par rapport aux murs gamma
    "short": 0.5,         # short interest élevé = carburant haussier / signal baissier
    "seasonality": 0.5,   # saisonnalité du mois
    "regime": 2.0,        # accord avec le market tide / secteur
    "earnings": 1.0,      # pénalité si résultats dans la fenêtre
}


@dataclass
class Candidate:
    ticker: str
    alerts: list[FlowAlert] = field(default_factory=list)
    screener: list[ScreenerHit] = field(default_factory=list)
    dark_pool: list[DarkPoolPrint] = field(default_factory=list)
    oi_changes: list[OIChange] = field(default_factory=list)
    insiders: list[InsiderTx] = field(default_factory=list)
    congress: list[CongressTx] = field(default_factory=list)
    context: TickerContext | None = None
    # résultats
    direction: str = ""  # up | down
    score: float = 0.0
    factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def bull_premium(self) -> float:
        return sum(a.premium for a in self.alerts if a.bullish)

    @property
    def bear_premium(self) -> float:
        return sum(a.premium for a in self.alerts if not a.bullish)

    @property
    def sources(self) -> list[str]:
        s = []
        if self.alerts:
            s.append("flux")
        if self.screener:
            s.append("screener")
        if self.dark_pool:
            s.append("dark pool")
        if self.oi_changes:
            s.append("OI")
        if self.insiders:
            s.append("initiés")
        if self.congress:
            s.append("congrès")
        return s


def regrouper(alerts: list[FlowAlert], screener: list[ScreenerHit], dark_pool: list[DarkPoolPrint],
              oi_changes: list[OIChange], insiders: list[InsiderTx], congress: list[CongressTx]
              ) -> dict[str, Candidate]:
    c: dict[str, Candidate] = defaultdict(lambda: Candidate(ticker=""))
    for a in alerts:
        c[a.ticker].ticker = a.ticker
        c[a.ticker].alerts.append(a)
    for h in screener:
        c[h.ticker].ticker = h.ticker
        c[h.ticker].screener.append(h)
    for d in dark_pool:
        c[d.ticker].ticker = d.ticker
        c[d.ticker].dark_pool.append(d)
    for o in oi_changes:
        c[o.ticker].ticker = o.ticker
        c[o.ticker].oi_changes.append(o)
    for i in insiders:
        c[i.ticker].ticker = i.ticker
        c[i.ticker].insiders.append(i)
    for g in congress:
        c[g.ticker].ticker = g.ticker
        c[g.ticker].congress.append(g)
    return dict(c)


def preselection(cands: dict[str, Candidate], n: int) -> list[Candidate]:
    """Les n tickers les plus « chauds » avant enrichissement : prime nette de flux + nombre de sources."""
    def chaleur(c: Candidate) -> float:
        net = abs(c.bull_premium - c.bear_premium)
        return math.log1p(net / 10_000) + 2.0 * (len(c.sources) - 1) + (1.0 if c.screener else 0.0)
    return sorted(cands.values(), key=chaleur, reverse=True)[:n]


# --- facteurs -------------------------------------------------------------------------

def facteur_flux(c: Candidate) -> tuple[float, float]:
    """(direction du flux -1..1, qualité 0..1)."""
    net = c.bull_premium - c.bear_premium
    f = math.tanh(net / 1_500_000)
    if not c.alerts:
        return 0.0, 0.0
    q = 0.0
    for a in c.alerts:
        w = 0.0
        if a.has_sweep:
            w += 0.35
        if a.rule == "RepeatedHitsAscendingFill" and a.type == "call" or \
           a.rule == "RepeatedHitsDescendingFill" and a.type == "put":
            w += 0.25
        if a.open_interest and a.volume > a.open_interest:
            w += 0.25
        if a.all_opening:
            w += 0.15
        q += min(w, 1.0) * a.premium
    tot = sum(a.premium for a in c.alerts) or 1.0
    return f, q / tot


def facteur_screener(c: Candidate) -> float:
    if not c.screener:
        return 0.0
    s = sum(1 if h.bullish else -1 for h in c.screener)
    return max(-1.0, min(1.0, s / 2))


def facteur_greek_flow(ctx: TickerContext | None) -> float:
    if ctx is None:
        return 0.0
    return math.tanh((ctx.net_call_premium - ctx.net_put_premium) / 3_000_000)


def facteur_oi(c: Candidate, ctx: TickerContext | None) -> float:
    call = sum(o.premium_change for o in c.oi_changes if o.type == "call" and o.oi_change > 0)
    put = sum(o.premium_change for o in c.oi_changes if o.type == "put" and o.oi_change > 0)
    if ctx is not None:
        call += ctx.oi_change_call_prem
        put += ctx.oi_change_put_prem
    return math.tanh((call - put) / 2_000_000)


def facteur_dark_pool(c: Candidate, ctx: TickerContext | None) -> float:
    """Confirmation 0..1 : blocs dark pool importants par rapport au volume moyen."""
    prem = sum(d.premium for d in c.dark_pool) + (ctx.dark_pool_premium_1d if ctx else 0.0)
    if ctx and ctx.avg_volume and ctx.price:
        ratio = prem / max(ctx.avg_volume * ctx.price, 1.0)  # part d'une journée moyenne
        return min(1.0, ratio / 0.10)
    return min(1.0, prem / 50_000_000)


def facteur_insider(c: Candidate, ctx: TickerContext | None) -> float:
    buy = sum(i.value for i in c.insiders if i.is_buy) + (ctx.insider_buy_value_30d if ctx else 0.0)
    sell = sum(i.value for i in c.insiders if not i.is_buy) + (ctx.insider_sell_value_30d if ctx else 0.0)
    if buy == 0 and sell == 0:
        return 0.0
    # les ventes d'initiés sont banales (stock-options) : pondérées moitié moins
    return math.tanh((buy - 0.5 * sell) / 2_000_000)


def facteur_congress(c: Candidate, ctx: TickerContext | None) -> float:
    b = sum(1 for g in c.congress if g.is_buy) + (ctx.congress_buys_60d if ctx else 0)
    s = sum(1 for g in c.congress if not g.is_buy) + (ctx.congress_sells_60d if ctx else 0)
    return max(-1.0, min(1.0, (b - s) / 3))


def facteur_analyst(ctx: TickerContext | None) -> float:
    if ctx is None:
        return 0.0
    return max(-1.0, min(1.0, (ctx.analyst_upgrades - ctx.analyst_downgrades) / 3))


def facteur_tendance(ctx: TickerContext | None) -> float:
    if ctx is None or not ctx.price or not ctx.sma20 or not ctx.sma50:
        return 0.0
    f = 0.0
    f += 0.5 if ctx.price > ctx.sma20 else -0.5
    f += 0.5 if ctx.price > ctx.sma50 else -0.5
    return f


def facteur_gex(ctx: TickerContext | None, direction: int) -> float:
    """Murs gamma : support (put wall) sous le prix favorise la hausse, résistance proche la freine."""
    if ctx is None or not ctx.price or direction == 0:
        return 0.0
    f = 0.0
    atr = ctx.atr14 or ctx.price * 0.02
    if ctx.call_wall and ctx.put_wall:
        if direction > 0:
            if ctx.call_wall - ctx.price < 0.5 * atr and ctx.call_wall > ctx.price:
                f -= 0.6  # juste sous une résistance gamma
            if 0 < ctx.price - ctx.put_wall < 1.5 * atr:
                f += 0.4  # appuyé sur un support gamma
            if ctx.price > ctx.call_wall:
                f += 0.5  # au-dessus du call wall : dealers chassent la hausse
        else:
            if ctx.price - ctx.put_wall < 0.5 * atr and ctx.put_wall < ctx.price:
                f -= 0.6
            if 0 < ctx.call_wall - ctx.price < 1.5 * atr:
                f += 0.4
            if ctx.price < ctx.put_wall:
                f += 0.5
    if ctx.gex_net is not None and ctx.gex_net < 0:
        f += 0.2  # gamma négatif : le mouvement en cours tend à s'amplifier
    return max(-1.0, min(1.0, f))


def facteur_short(ctx: TickerContext | None, direction: int) -> float:
    if ctx is None or ctx.short_interest_pct is None:
        return 0.0
    si = ctx.short_interest_pct
    if direction > 0:
        return min(1.0, si / 0.20)  # squeeze possible
    return min(0.5, si / 0.40)  # les vendeurs à découvert ont souvent raison, mais modérément


def facteur_saison(ctx: TickerContext | None, direction: int) -> float:
    if ctx is None or ctx.seasonality_month_avg is None:
        return 0.0
    f = math.tanh(ctx.seasonality_month_avg / 0.05)
    return f if direction > 0 else -f


def facteur_regime(regime: Regime, ctx: TickerContext | None, direction: int) -> float:
    if direction == 0:
        return 0.0
    b = regime.bias
    if ctx and ctx.sector and ctx.sector in regime.sector_bias:
        b = 0.5 * b + 0.5 * regime.sector_bias[ctx.sector]
    return b * direction  # accord > 0, désaccord < 0


def facteur_resultats(ctx: TickerContext | None, today: dt.date, max_dte: int) -> float:
    """Pénalité (≤ 0) si les résultats tombent dans la fenêtre du trade."""
    if ctx is None or ctx.next_earnings is None:
        return 0.0
    j = (ctx.next_earnings - today).days
    if j < 0:
        return 0.0
    if j <= 3:
        return -1.0
    if j <= max_dte:
        return -0.4
    return 0.0


def noter(c: Candidate, regime: Regime, today: dt.date, max_dte: int) -> Candidate:
    """Calcule direction, score (0..100) et facteurs explicatifs."""
    ctx = c.context
    flux, qualite = facteur_flux(c)
    directionnels = {
        "flow": flux,
        "screener": facteur_screener(c),
        "greek_flow": facteur_greek_flow(ctx),
        "oi_change": facteur_oi(c, ctx),
        "insider": facteur_insider(c, ctx),
        "congress": facteur_congress(c, ctx),
        "analyst": facteur_analyst(ctx),
        "trend": facteur_tendance(ctx),
    }
    brut = sum(POIDS[k] * v for k, v in directionnels.items())
    direction = 1 if brut > 0 else (-1 if brut < 0 else 0)
    if direction == 0:
        c.direction, c.score, c.factors = "", 0.0, directionnels
        c.reasons = ["aucune direction"]
        return c
    confirmations = {
        "flow_quality": qualite * (1 if flux * direction > 0 else -1),
        "dark_pool": facteur_dark_pool(c, ctx),
        "gex": facteur_gex(ctx, direction),
        "short": facteur_short(ctx, direction),
        "seasonality": facteur_saison(ctx, direction),
        "regime": facteur_regime(regime, ctx, direction),
        "earnings": facteur_resultats(ctx, today, max_dte),
    }
    total = abs(brut) + sum(POIDS[k] * v for k, v in confirmations.items())
    poids_max = sum(POIDS.values())
    score = 100 * max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(2.2 * total / poids_max)))
    if regime.risk_off:
        score *= 0.5
    c.direction = "up" if direction > 0 else "down"
    c.score = round(score, 1)
    c.factors = {**directionnels, **confirmations}
    c.reasons = _explications(c, ctx)
    return c


def _explications(c: Candidate, ctx: TickerContext | None) -> list[str]:
    r = []
    if c.alerts:
        r.append(f"flux {'haussier' if c.bull_premium >= c.bear_premium else 'baissier'} "
                 f"{max(c.bull_premium, c.bear_premium) / 1e6:.1f} M$ sur {len(c.alerts)} alertes")
    if c.screener:
        r.append("screener : " + ", ".join(sorted({h.preset for h in c.screener})))
    if ctx:
        if ctx.net_call_premium or ctx.net_put_premium:
            r.append(f"net premium jour calls {ctx.net_call_premium / 1e6:+.1f} M$ / puts {ctx.net_put_premium / 1e6:+.1f} M$")
        if ctx.call_wall and ctx.put_wall:
            r.append(f"murs gamma {ctx.put_wall:.0f} / {ctx.call_wall:.0f}")
        if ctx.iv_rank is not None:
            r.append(f"IV rank {ctx.iv_rank:.0%}")
        if ctx.next_earnings:
            r.append(f"résultats {ctx.next_earnings.isoformat()}")
        if ctx.short_interest_pct:
            r.append(f"short interest {ctx.short_interest_pct:.0%}")
        if ctx.insider_buy_value_30d:
            r.append(f"achats d'initiés {ctx.insider_buy_value_30d / 1e6:.1f} M$ (30 j)")
        if ctx.dark_pool_premium_1d:
            r.append(f"dark pool {ctx.dark_pool_premium_1d / 1e6:.0f} M$")
    for k, v in sorted(c.factors.items(), key=lambda kv: -abs(POIDS[kv[0]] * kv[1]))[:3]:
        r.append(f"{k} {v:+.2f}")
    return r
