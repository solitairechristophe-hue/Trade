# Famille GEX (dealer gamma) — backtest point-in-time

Fichier : `reports/backtest/gex.csv` (136 lignes = panel `calibration-signaux.csv`, 17 dates du 2026-08-06 au 2026-09-22, 70 tickers).

## Couverture
| Colonne | Lignes remplies |
|---|---|
| call_wall / put_wall / gamma_flip / gamma_magnet / gex_source | 132 / 136 |
| gex_net, gex_net_chg5 | 136 / 136 |
| dist_call_wall_atr, dist_put_wall_atr, above_flip | 132 / 136 |
| max_pain_nearest | 136 / 136 |

Les 4 trous (niveaux GEX vides) sont EYPT 2026-08-06, ASML 2026-08-10, CRDO 2026-08-14 et DASH 2026-08-20. `get_gex_levels` renvoie des champs nuls en `oi` comme en `vol`, et aussi à J-1. Les lignes sont gardées, avec ces colonnes vides.

`panel_screener.csv` : seules ses 62 lignes avec `close_t` ont des données exploitables. Ce sont les mêmes paires (date, ticker) que celles du panel flow, et elles sont toutes couvertes. Les 694 autres lignes n'ont ni close ni ATR : je ne les ai pas interrogées (environ 3 appels par ligne).

## Sources et définitions
- **Niveaux** : `get_gex_levels(ticker, date=D, source="oi")`. `oi` est utilisé partout (`gex_source=oi`). L'horodatage renvoyé est D à 19:59Z ou 20:14Z, soit la clôture américaine de D.
- **gex_net** = `call_gamma + put_gamma` à D, tiré de `get_greek_exposure_by_ticker` (série quotidienne). **gex_net_chg5** = gex_net(D) − gex_net(D − 5 séances). Le calendrier exclut le 7 septembre (Labor Day).
- **max_pain_nearest** : `get_max_pain(ticker, date=D)` renvoie le max pain par échéance tel qu'il était à D. On retient la première échéance ≥ D + 14 jours calendaires, quotidiennes et hebdomadaires comprises (pas seulement les mensuelles).
- **dist_*_atr** utilisent `close_t` et `atr14` du panel. **above_flip** = 1 si close_t > gamma_flip.

## Les dates passées fonctionnent-elles vraiment ?
Oui, pour les trois outils :
- les niveaux changent d'une date à l'autre, et l'horodatage correspond à la clôture de D ;
- le `close` renvoyé par `get_max_pain` est égal à `close_t` du panel (par exemple SPY 2026-08-06 : 768.56 des deux côtés) ;
- la série greek s'arrête bien à la date demandée.

Piège de l'API : le paramètre `timeframe` de `get_greek_exposure_by_ticker` est compté à partir d'aujourd'hui, et non à partir de `date`. Avec `date=2026-07-31&timeframe=1W`, la réponse est vide. Il faut donc une fenêtre assez longue (3M, 9W…).

## Risques de look-ahead et limites
- Les **niveaux GEX** et le **gex_net** sont calculés à la clôture de D. Un signal utilisable à D n'est donc tradable qu'à l'ouverture de D+1, pas à la clôture de D (même convention que `close_t`).
- La **série greek** peut avoir été recalculée après coup par UW (révisions d'OI ou de méthodologie). Je ne peux pas le vérifier. C'est un risque faible, mais il existe.
- **Murs aberrants** : le call wall est cherché au-dessus du spot et le put wall en dessous, parfois très loin. Exemples : SPY put_wall 641, AMAT 175, QQQ 584.78, TSM 150. On compte 31 lignes avec dist_put_wall_atr > 5 et 15 avec dist_call_wall_atr > 5. Mieux vaut plafonner (par exemple à 5 ATR) ou transformer en log avant tout usage.
- Quelques distances négatives (1 call, 3 put) : le mur est de l'autre côté de close_t. Cela vient de petits écarts entre le spot UW et `close_t`.
- **gex_net** est en unités brutes UW, non normalisées (de quelques milliers pour LITE ou ASML à plusieurs millions pour SPY ou EWZ). Pour comparer entre tickers, il faut normaliser, par exemple par sa moyenne roulante ou en z-score par ticker.
- Le max pain d'une échéance lointaine reflète l'OI de D. Il n'y a pas de fuite, mais l'information est bruitée sur les échéances peu liquides.
