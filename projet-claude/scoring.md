# Référence : scoring (extrait de scanner/scoring.py)

```python
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
    "liquidity": 0.75,    # option liquide vs action peu liquide (Muravyev, Pearson, Pollet 2025)
}

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

```
