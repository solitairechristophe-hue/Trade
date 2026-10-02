# Famille prix / volatilité / prime options / liquidité, en point-in-time

Fichier : `prix_vol.csv`, 830 lignes (date, ticker) uniques. Il couvre `calibration-signaux.csv` (136 lignes) et `panel_screener.csv` (756 lignes, dont 62 déjà présentes dans le premier panel). On compte 17 dates du 2026-08-06 au 2026-09-22 et 361 tickers.

## Ce qui a fonctionné pour les dates passées

- **`get_stock_screener(date=D, ticker=liste)`** renvoie bien un instantané historique de fin de séance D. Le champ `date` vaut D, et le `close` correspond à la clôture de D sur 870 contrôles (écart ≤ 0,5 %). Toutes les lignes du panel sont couvertes. Le repli sur `get_greek_flow_by_ticker` n'a donc pas servi.
  - Champs repris : `net_call_premium`, `net_put_premium`, `call_volume`, `put_volume`, `stock_volume`, `iv_rank`, `iv30d`, `marketcap`, `put_call_ratio`, et `issue_type` (ETF → `is_etf=1`, ADR et Common Stock → 0).
  - `implied_move_7` = `implied_move_perc_7` du screener, en fraction du prix (0,05 = 5 %). Une valeur négative (MBB, 09-18) a été mise à vide.
  - `os_ratio` = (call_volume + put_volume) × 100 / stock_volume.
- **Prix (tendance)** : barres journalières Massive « grouped daily » (`/v2/aggs/grouped/...`), soit 86 séances du 2026-05-20 au 2026-09-22, ajustées des splits. Elles servent à calculer `sma20`, `sma50` (moyennes simples des clôtures jusqu'à D inclus), `rsi14` (Wilder), `ret5` = C(D)/C(D−5) − 1 et `ret20`.
  - Contrôle : les clôtures Massive égalent `close_t` des panels.
  - L'historique UW `get_ticker_ohlc_latest_or_date` a été abandonné comme source principale : il n'est pas ajusté du reverse split de DLLL (écart d'environ 87 % avant juin).
- **`dist_sma20_atr`** = (C(D) − sma20) / atr14. On prend l'`atr14` du panel s'il existe. Sinon, l'ATR14 est recalculé (moyenne simple du true range sur 14 séances, à partir des barres H/L Massive). Il reproduit l'`atr14` du panel à 0,01 % près sur 136 lignes.
- **`vol_ratio`** = volume(D) / moyenne des volumes des 20 séances **précédant** D (D exclu), volumes consolidés Massive. Ces volumes sont identiques aux agrégats par ticker sur 4 329 points.

## Lacunes

- `sma50` manque pour SKHY (coté vers le 13/07) et SPCX (coté vers le 12/06) jusqu'à mi-août. `sma20` manque pour SKHY au 08-06.
- `put_call_ratio` est vide sur 4 lignes (DCI, MBB, EUFN, TCBI) : aucun volume put/call.
- `rsi14` démarre au plus tôt le 05-20 : la mise à l'échelle Wilder est courte mais suffisante (≥ 50 barres pour la plupart des tickers).

## Risques de look-ahead

- **`avg30_volume` et `relative_volume` du screener ne sont PAS point-in-time** : la valeur est identique quelle que soit la date demandée, c'est la valeur actuelle. Je ne les ai pas utilisés et j'ai recalculé `vol_ratio` moi-même.
- **`marketcap`** = prix de D × nombre d'actions **actuel**. Le look-ahead est faible (rachats et émissions), acceptable pour un tri par taille.
- **`stock_volume` du screener** ≈ 0,88 × le volume consolidé (médiane). C'est probablement le volume en séance régulière ou lit uniquement. `os_ratio` est donc légèrement surestimé, mais de façon homogène d'une ligne à l'autre.
- Les prix Massive sont ajustés **aujourd'hui** des splits survenus après D. Les ratios (rendements, RSI, distance en ATR) restent invariants. En revanche, les niveaux absolus `sma20` et `sma50` peuvent différer du prix réellement coté à D si un split est intervenu après D.
- Le screener est un instantané de **fin de séance D** : un signal pris à 11h30 le jour D ne voyait qu'une partie de ces flux. Pour un run du matin, il faut décaler ces colonnes d'une séance (utiliser D−1).
- D'autres champs du screener (par exemple `next_earnings_date` et `last_earnings_date` pour NVDA) paraissent recalculés après coup. Ils ne sont pas repris ici.

Script de construction : `/tmp/claude-0/-home-user-Trade/0878910c-e103-508a-9a4b-fbcdb0955593/scratchpad/build_prix_vol.py` (sources brutes dans le même dossier).
