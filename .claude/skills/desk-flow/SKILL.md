---
name: desk-flow
description: Run horaire du Desk Flow depuis Claude avec les connecteurs Unusual Whales (100 % des flux) et IBKR — régime de marché, meilleures opportunités, ordres calculés (spreads verticaux dimensionnés sur la NAV), instructions d'ordre créées dans IBKR et tickets déposés pour le robot.
---

# Desk Flow (connecteurs) — run horaire

Même logique que le scanner Python (`scanner/`), exécutée ici avec les **connecteurs** Unusual Whales et IBKR.
Le code de référence fait foi pour les formules : `scanner/scoring.py` (poids), `scanner/structure.py`
(structure et niveaux), `scanner/sizing.py` (taille et espérance), `tickets/README.md` (format).

Règles absolues : aucun ordre réel n'est transmis (une **instruction** IBKR est un brouillon que
l'utilisateur soumet lui-même ; le robot, lui, exécute les tickets selon `DRY_RUN`) ; les
garde-fous du robot s'appliquent (risque ≤ 2 % NAV, prime ≤ 3 % NAV, risque cumulé ≤ 10 %, 3 ordres/jour,
5 contrats, un trade par titre) ; au plus 3 tickets par run ; rien sur un titre déjà en position,
déjà proposé aujourd'hui, ou proposé dans les 3 derniers jours.

## 0. Préparation

1. Dépôt : `git fetch origin && git checkout <branche de travail>` (celle qui contient ce skill), `git pull --ff-only`.
2. Lire `reports/ia/dernier-flow-ia.md` et `tickets/<aujourd'hui>-flow-ia.json` s'ils existent (titres déjà proposés).
3. IBKR : `get_account_summary` (NAV = `net_liquidation`), `get_account_positions` (titres à exclure),
   `get_order_instructions` (instructions déjà créées : ne pas doubler).
4. Heure de New York ; si le marché est fermé, le run produit quand même le rapport (données de la veille).

## 1. Régime de marché (flux globaux)

- `get_market_tide` (pente de la dernière heure et niveau du jour : net call − net put premium) ;
- `get_market_sector_tide` pour les secteurs des candidats ; `get_market_etf_tide` SPY et QQQ ;
- `get_gex_levels` SPY et `get_greek_exposure_by_ticker` SPY (gamma positif = calme, négatif = nerveux) ;
- `get_market_events` et `get_market_state` / `get_trading_states` : événement macro dans les 2 h → **risk-off**
  (rapport seulement, aucun ticket) ; `get_yield_curve`, `get_central_bank_rates` si doute macro.

Biais = 0,6 × pente du tide (tanh(Δ/50 M$)) + 0,4 × niveau (tanh(niveau/150 M$)), borné à ±1.

## 2. Découverte des candidats (tous les flux)

- `get_flow_alerts` : `newer_than` = il y a 90 min (20 h avant l'ouverture), `min_premium` 50 000,
  `min_dte` 5, `max_dte` 90, `issue_types` Common Stock/ADR/ETF, `order` premium, `limit` 200 ;
- `get_options_screener` presets « Unusually Bullish », « Unusually Bearish », « Deep Conviction Calls/Puts » ;
- `get_dark_pool_trades` (blocs ≥ 5 M$), `get_open_interest_changes` (marché), `get_insider_transactions`
  (achats P / ventes S ≥ 200 k$, 14 j), `get_recent_congress_trades`, `get_analyst_ratings` (30 j),
  `get_stock_screener` (prix 2 ATR au-dessus de l'EMA20, volume > 1,5 × moyenne), `get_option_stance_ranking`,
  `get_upcoming_earnings` (titres à éviter dans la fenêtre), `get_market_seasonality`.

Univers : actions/ADR/ETF, prix 8–1 500 $, capitalisation ≥ 2 Md$ (ETF exemptés). Un dossier s'ouvre
seulement avec du flux d'options (alertes, screener ou OI) ; dark pool, initiés et Congrès confirment.
Garder les 10–15 titres les plus chauds (prime nette de flux × nombre de sources).

## 3. Enrichissement par titre (un appel par flux)

`get_company_info`, `get_ticker_ohlc_latest_or_date` + `get_ticker_candles_by_range` (60 j : SMA20/50, ATR14,
volume moyen), `get_ticker_indicator_series` (RSI14), `get_gex_levels` (call wall / put wall), `get_greek_exposure_by_ticker`,
`get_greek_flow_by_ticker`, `get_flow_per_strike`, `get_flow_per_expiry`, `get_open_interest_changes` (titre),
`get_dark_pool_volume_price_group`, `get_short_data_by_ticker`, `get_max_pain`, `get_implied_volatility_term_structure`
(IV rank), `get_earnings_history` / prochaine date de résultats, `get_insider_activity_by_ticker`,
`get_institutional_ownership_by_ticker`, `get_average_return_per_month_by_ticker`, `get_analyst_ratings` (titre),
puis la chaîne : `get_options_chain` / `get_chains_for_expiry` / `get_atm_chains` (bid, ask, delta, OI, volume).

## 4. Score de confluence (0–100) et direction

Facteurs directionnels (−1..+1) × poids : flux 3 (tanh(net/1,5 M$)), screener 1,5, net premium du jour 1,5,
variations d'OI 1, initiés 1, Congrès 0,5, analystes 0,5, tendance 1,5 (prix vs SMA20/50).
Direction = signe de la somme. Confirmations × poids : qualité du flux 1 (sweeps, fills ascendants, vol > OI,
ouverture), dark pool 1, murs gamma 1, short interest 0,5, saisonnalité 0,5, accord avec le régime 2
(biais marché/secteur × direction), résultats −1 (≤ 3 j) ou −0,4 (dans la fenêtre).
Score = 100 × (0,5 + 0,5 × tanh(2,2 × total / 18)), divisé par 2 en risk-off. Seuil : **55**.

## 5. Structure, niveaux, taille

- Échéance 21–50 jours qui n'enjambe pas les résultats (sinon ≥ 10 j avant les résultats, sinon on passe).
- IV rank < 55 % → **débit** : longue ~delta 0,50, courte ~delta 0,25 ou au mur gamma (0,8–2,5 ATR) ;
  limite = mid + 15 % du spread, plafond = limite × 1,07, TP = limite + 55 % × (largeur − limite),
  SL = 50 % de la limite ; prime = limite × 100 ; risque = (limite − SL) × 110.
- IV rank ≥ 55 % → **crédit** (bull put / bear call) : courte ~delta 0,25, longue ≤ 2 ATR plus loin, crédit ≥ 20 % de
  la largeur ; limite = mid − 15 % du spread, plafond = limite, TP = 50 % du crédit, SL = 2 × crédit ;
  jambes décrites dans le sens débit, `side` = SELL.
- Liquidité : spread ≤ max(0,10 ; 15 % du mid), OI ou volume ≥ 50.
- Condition d'entrée : action ≥ prix + 0,15 ATR (hausse) / ≤ prix − 0,15 ATR (baisse) ; stop action = 1,5 ATR
  (ou juste au-delà du mur gamma) ; sortie temps = échéance − 7 j.
- Quantité = min(2 % NAV / risque par combo, 3 % NAV / prime par combo (débit), 5) ; 0 → écarté.
- p(gain) = 0,38 + 0,24 × score/100 ; EV = p × gain TP − (1 − p) × perte SL ; **classer par EV / $ risqué**,
  garder au plus 3 (et le quota journalier restant), EV > 0 seulement.

## 6. Vérification et instructions IBKR

Pour chaque ticket retenu : `search_contracts` (ligne au symbole exact), `get_option_parameters`,
`get_option_data` (échéance, bornes de strikes), `get_price_snapshot` des deux jambes (bid/ask réels : si le mid
IBKR s'écarte de plus de 10 % du mid UW, recalculer limite/TP/SL avec IBKR), `get_combo_identifier`, puis
`create_order_instruction` (LIMIT, `limit_price` = limite, `quantity`, `side` = BUY pour un débit / SELL pour un crédit,
`time_in_force` DAY). Noter l'URL de l'instruction dans le rapport. Jamais plus de 3 instructions par run.

## 7. Sorties

1. `tickets/<AAAA-MM-JJ>-flow-ia.json` (desk `flow-ia`, format `tickets/README.md`, ids `flow-ia-<date>-<SYM>`,
   ajouter au fichier du jour sans doublon) — le robot du VPS les exécute.
2. `reports/ia/<AAAA-MM-JJ>-<HHMM>-flow-ia.md` + copie `reports/ia/dernier-flow-ia.md` : régime, tableau des
   opportunités (titre, sens, structure, qté, limite, plafond, TP, SL, prime, risque, score, p, EV, URL IBKR),
   candidats écartés et raisons, flux utilisés, erreurs de connecteur.
3. `git add tickets reports/ia && git commit -m "Desk Flow <date> <HHMM>" && git push -u origin <branche>`.
4. Message final : les opportunités retenues en 3 lignes maximum chacune, puis « aucune » le cas échéant.
