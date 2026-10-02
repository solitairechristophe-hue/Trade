# Backtest — signaux Options Screener (UW), 17 dates

Source : `get_options_screener` à date passée (snapshot vérifié par date), 4 presets top-25 (Common Stock/ADR/ETF). Direction = signe(Σ prime × sens preset). Issue identique au panel flow : clôture t+7 séances, ATR14, move_atr = (c7−c)·dir/ATR. IC = Wilson 95 %. Hasard = ½ × part des |move| ≥ seuil (½ pour la direction).

| Groupe | n | Gain ≥ 1 ATR | Gain ≥ 0,5 ATR | Direction |
|---|---|---|---|---|
| Tous signaux screener | 756 | 28% [25–31] (hasard 26%) | 38% [35–41] (hasard 36%) | 52% [48–55] (hasard 50%) |
| Screener seul (hors panel flow) | 694 | 28% [25–31] (hasard 26%) | 38% [35–42] (hasard 36%) | 52% [48–55] (hasard 50%) |
| Preset Unusually Bullish | 296 | 27% [23–33] (hasard 28%) | 34% [29–40] (hasard 36%) | 48% [42–54] (hasard 50%) |
| Preset Deep Conviction Calls | 45 | 18% [9–31] (hasard 26%) | 29% [18–43] (hasard 38%) | 47% [33–61] (hasard 50%) |
| Preset Unusually Bearish | 251 | 30% [25–36] (hasard 24%) | 41% [36–48] (hasard 34%) | 56% [50–62] (hasard 50%) |
| Preset Deep Conviction Puts | 64 | 22% [14–33] (hasard 21%) | 44% [32–56] (hasard 38%) | 56% [44–68] (hasard 50%) |
| Haussiers (dir +1) | 390 | 27% [23–32] (hasard 28%) | 35% [31–40] (hasard 37%) | 49% [45–54] (hasard 50%) |
| Baissiers (dir −1) | 366 | 28% [24–33] (hasard 24%) | 41% [36–46] (hasard 36%) | 54% [49–59] (hasard 50%) |
| Multi-presets (n_presets ≥ 2) | 100 | 31% [23–41] (hasard 27%) | 41% [32–51] (hasard 40%) | 51% [41–61] (hasard 50%) |
| Flow ∩ screener, même direction | 37 | 24% [13–40] (hasard 22%) | 35% [22–51] (hasard 36%) | 51% [36–67] (hasard 50%) |
| Flow ∩ screener, direction opposée | 25 | 32% [17–52] (hasard 32%) | 40% [23–59] (hasard 42%) | 48% [30–67] (hasard 50%) |

Lignes : 756 paires (date, ticker), 350 tickers ; 62 déjà dans le panel flow.
Limites : 2026-08-28 Deep Conviction Calls vide ; appartenance à un preset = top-25 seulement ; signaux fortement corrélés entre eux le même jour (IC optimistes).
