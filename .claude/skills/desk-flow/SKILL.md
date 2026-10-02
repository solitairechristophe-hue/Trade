---
name: desk-flow
description: Run du Desk Flow depuis Claude (mode matin par défaut, run manuel vers 11h30 à Paris, ordres conditionnels posés par l'utilisateur ; mode horaire en séance) avec les connecteurs Unusual Whales (100 % des flux) et IBKR — régime de marché, meilleures opportunités, ordres calculés (spreads verticaux dimensionnés sur la NAV), instructions d'ordre créées dans IBKR et tickets déposés pour le robot.
---

# Desk Flow (connecteurs)

Même logique que le scanner Python (`scanner/`), exécutée ici avec les **connecteurs** Unusual Whales et IBKR.
Le code de référence fait foi pour les formules : `scanner/scoring.py` (poids), `scanner/structure.py`
(structure et niveaux), `scanner/sizing.py` (taille et espérance), `tickets/README.md` (format).

Règles absolues : aucun ordre réel n'est transmis (une **instruction** IBKR est un brouillon que
l'utilisateur soumet lui-même ; le robot, lui, exécute les tickets selon `DRY_RUN`) ; les
garde-fous du robot s'appliquent (risque ≤ 2 % NAV, prime ≤ 3 % NAV, risque cumulé ≤ 10 %, 3 ordres/jour,
5 contrats, un trade par titre) ; au plus 3 tickets par run ; rien sur un titre déjà en position,
déjà proposé aujourd'hui, ou proposé dans les 3 derniers jours.

## Mode matin (par défaut) : run manuel vers 11h30 à Paris

L'utilisateur est en Europe, disponible le matin seulement. Il lance le run lui-même vers 11h30 à Paris
(5h30 à New York, 6h30 entre le dernier dimanche d'octobre et le premier dimanche de novembre, marché US fermé)
et pose lui-même les ordres conditionnels dans TWS. Personne ne surveille la séance. Ce mode s'applique dès que
le marché US est fermé ; les étapes ci-dessous s'appliquent avec ces changements :

- **Fenêtre de flux** : toute la séance US précédente (`newer_than` = ouverture 09:30 NY de la dernière séance,
  `date` = dernière séance pour le tide, les screeners et le dark pool), pas les 90 dernières minutes.
- **Open interest** : les variations de la veille sont publiées vers 6h45 NY (12h45 à Paris) ; à 11h30, celles
  disponibles datent de l'avant-veille. Les utiliser comme confirmation de second rang et le dire au rapport.
- **Préouverture** : à partir de 4h NY, le cours de l'action est disponible (`get_price_snapshot` IBKR champ
  `last`, ou dernière bougie UW). Condition d'entrée, stop action et filtres de prix partent de ce cours.
  Un gap de plus de 1 ATR contre le sens du trade depuis la clôture invalide le dossier.
- **Risk-off** : un événement majeur **dans la journée** (CPI, emploi, PCE, PPI à 8h30 NY = 14h30 Paris, FOMC,
  PIB, ISM, ventes au détail) suffit ; rapport seulement, aucun ordre.
- **Cotations d'options** : celles de la clôture de la veille (les options ne cotent pas avant 9h30 NY).
  Limite = mid de clôture + 15 % du spread, jamais au-dessus du plafond ; si la chaîne n'a ni bid ni ask,
  spread estimé à max(0,10 ; 10 % du mid) et le dire.
- **Taille sans surveillance** : le stop loss à 50 % de la prime ne peut pas être surveillé. Le risque retenu est
  la perte maximale du spread : prime entière pour un débit, (largeur − crédit) × 100 pour un crédit.
  Quantité = min(2 % NAV / perte maximale par combo, 5). `max_loss` du ticket = perte maximale.
  L'espérance se calcule avec cette perte maximale.
- **Quota** : les 3 trades du jour sont choisis dans ce seul run.

### Ordres à poser dans TWS (sortie principale du mode matin)

Pour chaque trade retenu, un bloc prêt à recopier :

1. **Combo** : symbole, échéance, strikes, achat/vente de chaque jambe, quantité, côté BUY (débit) ou SELL (crédit).
2. **Ordre d'entrée** : LIMIT au prix limite, TIF DAY.
3. **Condition** : « prix de <action> ≥ (ou ≤) <niveau> », méthode de déclenchement « Last », case
   « autoriser hors séance régulière » **décochée** (sinon un échange de préouverture peut déclencher l'ordre
   avant que les options cotent).
4. **Take profit** : ordre attaché « Profit Taker » LIMIT GTC au niveau TP.
5. **Stop sur l'action** : niveau de clôture qui invalide le trade ; proposer une alerte de prix IBKR
   (`create_alert`, seulement si l'utilisateur le demande) pour être prévenu sur le téléphone.
6. **Sortie temps** : date à laquelle fermer la position, quoi qu'il arrive.

Si l'utilisateur a demandé les instructions IBKR, créer en plus l'instruction (étape 6) : elle porte la limite et
la quantité ; la condition et le take profit restent à ajouter dans TWS au moment de la valider.

### Suivi des positions (chaque matin, avant la recherche)

Pour chaque position ouverte par le desk (`get_account_positions`, tickets `flow-ia` des jours précédents) :
valeur du combo à la clôture de la veille, distance au TP, clôture de l'action par rapport au stop, date de
sortie temps. Signaler en tête de rapport, avec l'ordre de clôture à poser (LIMIT DAY au mid de clôture) :
action clôturée au-delà du stop, sortie temps atteinte, résultats avant la prochaine séance, ou valeur du combo
sous 30 % de la prime payée (le reste ne vaut plus le risque).

## Mode horaire (en séance)

Marché ouvert : la procédure ci-dessous s'applique telle quelle.

## 0. Préparation

1. Dépôt : `git fetch origin && git checkout <branche de travail>` (celle qui contient ce skill), `git pull --ff-only`.
2. Lire `reports/ia/dernier-flow-ia.md` et `tickets/<aujourd'hui>-flow-ia.json` s'ils existent (titres déjà proposés).
3. IBKR : `get_account_summary` (NAV = `net_liquidation`), `get_account_positions` (titres à exclure),
   `get_order_instructions` (instructions déjà créées : ne pas doubler).
4. Heure de New York ; si le marché est fermé, le run produit quand même le rapport (données de la veille).
   Avant 09:45, les cotations d'options UW sont celles de la veille : ne retenir un ticket qu'après re-cotation
   des jambes chez IBKR (`get_price_snapshot`), sinon rapport seulement.

## 1. Régime de marché (flux globaux)

- `get_market_tide` (pente de la dernière heure et niveau du jour : net call − net put premium) ;
- `get_market_sector_tide` pour les secteurs des candidats ; `get_market_etf_tide` SPY et QQQ ;
- `get_gex_levels` SPY et `get_greek_exposure_by_ticker` SPY (gamma positif = calme, négatif = nerveux) ;
- `get_market_events` et `get_market_state` / `get_trading_states` : événement macro **majeur** (FOMC, CPI, PCE, PPI,
  NFP/emploi, PIB, ISM, ventes au détail, inscriptions au chômage) dans les 2 h → **risk-off** (rapport seulement,
  aucun ticket) ; les publications de second rang (Factory Orders…) ne comptent pas ; `get_yield_curve`,
  `get_central_bank_rates` si doute macro.

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
`get_dark_pool_volume_price_group`, `get_short_volume_ratio_by_ticker` et `get_short_screener` (short interest ;
`get_short_data_by_ticker` ne donne que le taux d'emprunt), `get_max_pain`, `get_implied_volatility_term_structure`
(IV rank), `get_earnings_history` / prochaine date de résultats, `get_insider_transactions` (`ticker_symbol`, codes P/S ;
`get_insider_activity_by_ticker` ne liste pas les transactions),
`get_institutional_ownership_by_ticker`, `get_average_return_per_month_by_ticker`, `get_analyst_ratings` (titre),
puis la chaîne : `get_options_chain` / `get_chains_for_expiry` / `get_atm_chains` (bid, ask, delta, OI, volume).

## 4. Score de confluence (0–100) et direction

Facteurs directionnels (−1..+1) × poids : flux 3 (tanh(net/1,5 M$)), screener 1,5, net premium du jour 1,5,
variations d'OI 1, initiés 1, Congrès 0,5, analystes 0,5, tendance 1,5 (prix vs SMA20/50).
Le flux est pondéré : une alerte dont l'échéance tombe 0 à 10 jours après les prochains résultats compte pour
moitié (les achats d'options informent avant les événements imprévus, pas avant les événements programmés).
Direction = signe de la somme. Confirmations × poids : qualité du flux 1 (sweeps, blocs « floor », fills
ascendants, vol > OI, ouverture), liquidité relative 0,75 (ratio O/S = contrats du jour × 100 / actions du jour :
tanh((O/S − 0,15)/0,15), −0,5 au-delà de 500 Md$ de capitalisation, −0,25 au-delà de 200 Md$ ; la prévisibilité
est forte quand l'option est liquide et l'action peu liquide), dark pool 1, murs gamma 1, short interest 0,5, saisonnalité 0,5, accord avec le régime 2
(biais marché/secteur × direction), résultats −1 (≤ 3 j) ou −0,4 (dans la fenêtre).
Score = 100 × (0,5 + 0,5 × tanh(2,2 × total / 18,75)), divisé par 2 en risk-off. Seuil : **55**.

## 5. Structure, niveaux, taille

- Échéances 21–50 jours qui n'enjambent pas les résultats (sinon ≥ 10 j avant les résultats, sinon on passe) :
  construire la structure sur chaque échéance valide et garder celle au meilleur gain/risque.
- IV rank < 55 % → **débit** : longue ~delta 0,50 (ou 0,40), courte ~delta 0,25 ou au mur gamma (0,8–2,5 ATR),
  largeur entre 0,5 et 3 ATR ; si la prime dépasse 3 % de la NAV, resserrer la largeur (courte plus proche) avant
  d'abandonner le titre ;
  limite = mid + 15 % du spread, plafond = limite × 1,07, TP = limite + 45 % × (largeur − limite),
  SL = 50 % de la limite ; prime = limite × 100 ; risque = (limite − SL) × 110.
- IV rank ≥ 55 % → **crédit** (bull put / bear call) : courte ~delta 0,25, longue ≤ 2 ATR plus loin, crédit ≥ 20 % de
  la largeur, largeur 0,5–2 ATR ; limite = mid − 15 % du spread, plafond = limite, TP = 50 % du crédit, SL = 1,5 × crédit
  (à 2 × l'espérance est négative pour p ≤ 0,69) ;
  jambes décrites dans le sens débit, `side` = SELL.
- Liquidité : spread ≤ max(0,10 ; 15 % du mid), OI ou volume ≥ 50.
- Condition d'entrée : action ≥ prix + 0,15 ATR (hausse) / ≤ prix − 0,15 ATR (baisse) ; stop action = 1,5 ATR
  (ou juste au-delà du mur gamma) ; **sortie temps = run + 10 jours calendaires (~7 séances)**, jamais après
  échéance − 7 j : la recherche trouve l'effet du flux sur quelques jours à une semaine, pas au-delà.
- Quantité = min(2 % NAV / risque par combo, 3 % NAV / prime par combo (débit), 5) ; 0 → écarté.
- p(gain) = p_min + (p_max − p_min) × score/100, avec p_min et p_max mesurés par la calibration
  (`reports/calibration.md`, `scanner/calibration.json`) ; à défaut 0,38 et 0,62 ; EV = p × gain TP − (1 − p) × perte SL ; **classer par EV / $ risqué**,
  garder au plus 3 (et le quota journalier restant), EV > 0 seulement.

## 6. Vérification et instructions IBKR

Pour chaque ticket retenu : `search_contracts` (ligne au symbole exact), `get_option_parameters`,
`get_option_data` (échéance, bornes de strikes), `get_price_snapshot` des deux jambes (bid/ask réels : si le mid
IBKR s'écarte de plus de 10 % du mid UW, recalculer limite/TP/SL avec IBKR), `get_combo_identifier`, puis
`create_order_instruction` (LIMIT, `limit_price` = limite, `quantity`, `side` = BUY pour un débit / SELL pour un crédit,
`time_in_force` DAY). Noter l'URL de l'instruction dans le rapport. Jamais plus de 3 instructions par run.

La création d'instructions est une action sur le compte : elle n'a lieu que si l'utilisateur l'a autorisée
dans la session (ou dans le prompt de la Routine). Sinon l'étape 6 reste en **lecture seule** : vérifier les jambes
et noter les identifiants de contrats IBKR (et le combo) dans le rapport, pour que l'utilisateur crée l'ordre lui-même.

## 7. Sorties

1. `tickets/<AAAA-MM-JJ>-flow-ia.json` (desk `flow-ia`, format `tickets/README.md`, ids `flow-ia-<date>-<SYM>`,
   ajouter au fichier du jour sans doublon) — le robot du VPS les exécute.
2. `reports/ia/<AAAA-MM-JJ>-<HHMM>-flow-ia.md` + copie `reports/ia/dernier-flow-ia.md` : régime, tableau des
   opportunités (titre, sens, structure, qté, limite, plafond, TP, SL, prime, risque, score, p, EV, URL IBKR),
   candidats écartés et raisons, flux utilisés, erreurs de connecteur.
3. `git add tickets reports/ia && git commit -m "Desk Flow <date> <HHMM>" && git push -u origin <branche>`.
4. Message final : les opportunités retenues en 3 lignes maximum chacune, puis « aucune » le cas échéant.
