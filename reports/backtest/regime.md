# Régime de marché — dataset point-in-time (backtest Desk Flow)

Fichier : `regime.csv` — 136 lignes (date, ticker) du panel `calibration-signaux.csv`, 17 dates du 2026-08-06 au 2026-09-22.

## Outils et dates passées
| Variable | Outil UW | Dates passées ? | Couverture |
|---|---|---|---|
| tide_pente / tide_niveau / tide_bias | `get_market_tide(date, interval_5m=false)` | oui | 136/136 |
| spy_tide / qqq_tide | `get_market_etf_tide(SPY/QQQ, date)` | oui | 136/136 |
| spy_gex_net / spy_gex_positive | `get_greek_exposure_by_ticker(SPY, date=2026-09-22, 3M)`, ligne = D | oui | 136/136 |
| macro_event_next_day | `get_market_events(min_date, max_date)` | oui (2026-08-06 → 2026-09-25) | 136/136 |
| sector | `get_stock_screener` (champ `sector`) + `get_company_info` (ASTS, LITE, ORCL) | statique | 94/136 (les 42 lignes vides sont des ETF : SPY, QQQ, IWM, GLD, SLV, SMH, XL*, EW*, IBIT, BNO, DLLL…) |
| sector_bias | `get_market_sector_tide(sector, date)` | oui | 94/94 lignes « action » |

Aucun outil n'a échoué.

## Méthode
- Pente = tanh(((call_T − call_T−60min) − (put_T − put_T−60min)) / 50 M$), niveau = tanh((call_T − put_T) / 150 M$), biais = 0,6·pente + 0,4·niveau. T = dernière minute ≤ 16:00 heure de New York.
- Données à la minute plutôt qu'en 5 min : une ligne 5 min horodatée T contient le cumul à T+4 min, donc la ligne « 16:00 » en 5 min intègre 16:01–16:04 (après la clôture). La version à la minute coupée à 16:00 respecte la règle point-in-time. Les valeurs diffèrent un peu de celles du robot en production (fenêtre de 12 barres de 5 min).
- `sector_bias` suit la consigne (0,6/0,4). Le code de production `scanner/regime.py::sector_biases` utilise 0,5/0,5 : à harmoniser si besoin.
- Macro J+1 (jour ouvré suivant, Labor Day 7/09 exclu) : CPI, PCE, PPI, rapport sur l'emploi/NFP, FOMC, GDP, ISM, ventes au détail. ADP, NFIB et PMI flash sont exclus. Résultat = 1 pour 08-06 (emploi), 08-12 (PPI), 08-18 (minutes FOMC), 09-03 (emploi), 09-10 (CPI).

## Lacunes et risques de look-ahead
- **Minutes FOMC (19/08) comptées comme événement majeur** : ce choix est discutable.
- **Le calendrier UW ne contient aucun GDP** sur la période (révision du T2 attendue vers le 27/08), ni d'ISM le 31/08 → `macro_event_next_day` pour 08-26 vaut peut-être 0 à tort. La date de la décision FOMC du 16/09 est J et non J+1 pour le panel.
- Calendrier lu aujourd'hui : seules les dates prévues sont utilisées (connues à l'avance) ; les valeurs « réalisées » ne sont pas utilisées.
- **Secteur** : la classification actuelle est appliquée à tout l'historique. C'est un look-ahead faible, puisque le secteur est quasi statique. HOOD est classé Technology et CIFR/WULF Financial Services selon UW.
- **GEX SPY** : la ligne quotidienne du jour D est calculée par UW sur la base de l'open interest du matin et de la clôture de D, donc elle est connue le soir de D. On ne peut pas vérifier que UW n'a pas recalculé ces valeurs a posteriori.
- Market/sector/ETF tide : séries intrajournalières publiées en temps réel. Le risque de révision a posteriori par UW n'est pas vérifiable.
