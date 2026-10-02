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

# Poids revus après le backtest croisé du 2 octobre 2026 (reports/backtest/synthese.md, 830 signaux, 17 séances).
# Seuls les murs gamma et le gamma des dealers ont tenu hors échantillon ; les facteurs sans effet mesuré
# gardent un petit poids, ceux à effet contraire sur la période ne pèsent presque plus.
POIDS = {
    "flow": 1.5,          # flux d'options : aucun avantage seul sur 2 mois (24 % vs 25 % au hasard)
    "flow_quality": 0.5,
    "screener": 1.0,      # presets : 28 % vs 26 % au hasard
    "greek_flow": 0.5,    # prime nette du jour : effet contraire sur la période
    "oi_change": 0.5,     # non testable à date (pas d'historique)
    "dark_pool": 0.5,
    "insider": 0.5,
    "congress": 1.0,      # stable sur les deux moitiés (33 % vs 17 %), à confirmer
    "analyst": 0.25,
    "trend": 0.5,         # aucun effet mesuré
    "gex": 3.0,           # murs gamma : 28 % quand favorables, 9 % quand contre, stable hors échantillon
    "gamma_neg": 1.5,     # gamma des dealers négatif : 33 % vs 23 %
    "short": 0.25,
    "seasonality": 0.25,  # mesure biaisée (statistiques calculées aujourd'hui)
    "regime": 0.5,        # accord avec le tide : effet contraire sur la période
    "earnings": 1.0,      # pénalité si résultats dans la fenêtre
    "liquidity": 0.75,    # option liquide vs action peu liquide (Muravyev, Pearson, Pollet 2025)
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

def poids_alerte(a: FlowAlert) -> float:
    """Le flux misant sur des résultats annoncés informe peu : achats d'options informatifs avant les
    événements imprévus, pas avant les événements programmés. Une échéance qui suit de près les
    résultats compte pour moitié."""
    if a.next_earnings and a.created_at:
        jours = (a.expiry - a.next_earnings).days
        if 0 <= jours <= 10 and a.next_earnings >= a.created_at.date():
            return 0.5
    return 1.0


def facteur_flux(c: Candidate) -> tuple[float, float]:
    """(direction du flux -1..1, qualité 0..1)."""
    net = sum(poids_alerte(a) * a.premium * (1 if a.bullish else -1) for a in c.alerts)
    f = math.tanh(net / 1_500_000)
    if not c.alerts:
        return 0.0, 0.0
    q = 0.0
    for a in c.alerts:
        w = 0.0
        if a.has_sweep:
            w += 0.30
        if a.has_floor:
            w += 0.15  # bloc négocié : flux institutionnel, moins dilué par les particuliers
        if a.rule == "RepeatedHitsAscendingFill" and a.type == "call" or \
           a.rule == "RepeatedHitsDescendingFill" and a.type == "put":
            w += 0.20
        if a.open_interest and a.volume > a.open_interest:
            w += 0.20
        if a.all_opening:
            w += 0.15
        q += min(w, 1.0) * a.premium * poids_alerte(a)
    tot = sum(a.premium * poids_alerte(a) for a in c.alerts) or 1.0
    return f, q / tot


def facteur_liquidite(ctx: TickerContext | None) -> float:
    """La prévisibilité est forte quand l'option est liquide et l'action peu liquide, faible dans le cas
    inverse. Ratio O/S = contrats × 100 / actions échangées ; les méga-capitalisations sont pénalisées."""
    if ctx is None:
        return 0.0
    f = 0.0
    if ctx.options_volume and ctx.stock_volume:
        os_ratio = ctx.options_volume * 100 / ctx.stock_volume
        f = math.tanh((os_ratio - 0.15) / 0.15)
    if ctx.marketcap >= 500e9:
        f -= 0.5
    elif ctx.marketcap >= 200e9:
        f -= 0.25
    return max(-1.0, min(1.0, f))


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


def _dist_murs(ctx: TickerContext, direction: int) -> tuple[float, float] | None:
    """(place jusqu'au mur dans le sens du trade, distance au mur d'appui), en ATR, plafonnées à 5."""
    if not (ctx.price and ctx.call_wall and ctx.put_wall):
        return None
    atr = ctx.atr14 or ctx.price * 0.02
    cap = lambda x: max(-5.0, min(5.0, x))
    dc, dp = cap((ctx.call_wall - ctx.price) / atr), cap((ctx.price - ctx.put_wall) / atr)
    return (dc, dp) if direction > 0 else (dp, dc)


def facteur_gex(ctx: TickerContext | None, direction: int) -> float:
    """Murs gamma, tels que testés : tanh(place) − 0,5 × tanh(appui). Positif = de la place jusqu'au mur
    dans le sens du trade et un appui proche derrière ; négatif = le trade bute sur un mur."""
    if ctx is None or direction == 0:
        return 0.0
    d = _dist_murs(ctx, direction)
    if d is None:
        return 0.0
    place, appui = d
    return max(-1.0, min(1.0, math.tanh(place) - 0.5 * math.tanh(appui)))


def facteur_gamma_negatif(ctx: TickerContext | None) -> float:
    if ctx is None or ctx.gex_net is None:
        return 0.0
    return 1.0 if ctx.gex_net < 0 else -1.0


def murs_contre(ctx: TickerContext | None, direction: int) -> bool:
    """Le trade bute sur un mur gamma : 9 à 15 % de réussite en backtest, sur chaque moitié et chaque panel."""
    return facteur_gex(ctx, direction) < -0.05


def setup_gamma(ctx: TickerContext | None, direction: int) -> bool:
    """Seul setup à espérance non négative mesurée : murs favorables ET gamma des dealers négatif."""
    return facteur_gex(ctx, direction) > 0 and facteur_gamma_negatif(ctx) > 0


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
        "gamma_neg": facteur_gamma_negatif(ctx),
        "short": facteur_short(ctx, direction),
        "seasonality": facteur_saison(ctx, direction),
        "regime": facteur_regime(regime, ctx, direction),
        "earnings": facteur_resultats(ctx, today, max_dte),
        "liquidity": facteur_liquidite(ctx),
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
