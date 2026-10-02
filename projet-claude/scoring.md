# Référence : scoring (extrait de scanner/scoring.py et scanner/volatilite.py)

```python
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
    "congress": 0.25,     # effet du backtest probablement artefactuel ; pas d'avantage agrégé (Belmont et al. 2022)
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

FAMILLE_FLUX = ("flow", "flow_quality", "screener", "greek_flow", "regime")
PLAFOND_FLUX = 1.5  # contribution maximale de toute la famille : ces signaux viennent des mêmes exécutions


def poids_echeance(dte: int) -> float:
    """Flux séparé par échéance : le très court terme est surtout spéculatif ou de couverture."""
    if dte < 7:
        return 0.0
    if dte < 21:
        return 0.5
    if dte <= 60:
        return 1.0
    return 0.75


def poids_alerte(a: FlowAlert) -> float:
    """Le flux misant sur des résultats annoncés informe peu : achats d'options informatifs avant les
    événements imprévus, pas avant les événements programmés. Une échéance qui suit de près les
    résultats compte pour moitié. Le poids dépend aussi de l'échéance (poids_echeance)."""
    w = poids_echeance(a.dte) if a.created_at else 1.0
    if a.next_earnings and a.created_at:
        jours = (a.expiry - a.next_earnings).days
        if 0 <= jours <= 10 and a.next_earnings >= a.created_at.date():
            w *= 0.5
    return w

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
```
