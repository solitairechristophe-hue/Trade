# Référence : scoring (extrait de scanner/scoring.py)

```python
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
```
