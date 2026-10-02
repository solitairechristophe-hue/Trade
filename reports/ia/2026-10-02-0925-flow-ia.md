# Desk Flow (connecteurs) — 2026-10-02 09:25 New York

Premier run réel de la procédure `desk-flow` (connecteurs Unusual Whales + IBKR). Marché pas encore ouvert
(ouverture 09:30) : les flux d'options sont ceux de la séance du 2026-10-01 (après 13:00 NY) et les
cotations d'options sont celles de la clôture de la veille ; les cours des sous-jacents sont ceux de la
pré-ouverture du 2026-10-02.

**Compte IBKR** : NAV 8 914 $ (`net_liquidation`), positions existantes ASX, NEE, SMCI (exclues),
aucune instruction d'ordre déjà créée. Budget par trade : risque ≤ 178 $ (+10 %), prime ≤ 267 $ (débit).

**Ce run est en lecture seule côté IBKR : aucune instruction d'ordre n'a été créée.** Le robot du VPS
exécute les tickets déposés dans `tickets/` selon `DRY_RUN`.

## 1. Régime de marché

| Flux | Lecture |
|---|---|
| Market tide (01/10, dernière heure) | net call −53,8 → −40,2 M$, net put −10,5 → −7,7 M$ : pente +10,9 M$ → tanh(+0,22) ; niveau de clôture (call − put) −32,4 M$ → tanh(−0,21) |
| **Biais** | 0,6 × 0,21 + 0,4 × (−0,21) = **+0,04 (neutre)** |
| ETF tide SPY / QQQ | SPY : call −22,1 M$, put −34,9 M$ (légèrement positif) ; QQQ : call −48,3 M$, put −34,9 M$ (légèrement négatif) |
| Secteurs (biais 0,5 × pente + 0,5 × niveau) | Technology **+0,60** ; Communication Services −0,37 ; Industrials −0,10 ; Consumer Cyclical −0,03 |
| SPY gamma | call gamma 3,35 M, put gamma −4,79 M → **gamma net négatif (régime nerveux)** ; flip 763,35, put wall 763, call wall 766, aimant 765 (spot 764) |
| Market state 01/10 | put/call 0,82, prime calls 21,5 Md$ / puts 17,1 Md$ |
| Événements | Employment Report / taux de chômage / salaires à 08:30 NY (déjà publiés) ; **Factory Orders à 10:00 NY** (dans les 2 h) |

Décision régime : **neutre, non risk-off**. Le seul événement dans les 2 h est Factory Orders
(publication de second rang) ; le NFP était déjà publié à 08:30. Le code de référence (`regime.py`)
marquerait pourtant *risk-off* (il ne distingue pas l'importance des événements) — point à trancher dans
le skill (voir fin de rapport). Les scores ci-dessous ne sont donc pas divisés par deux.

## 2. Découverte (flux du 01/10 après 13:00 NY)

- `get_flow_alerts` (50 alertes ≥ 50 k$, 5–90 DTE) : prime nette par titre — AMD −7,5 M$, TLT −5,8 M$,
  IWM −4,4 M$, MU +4,0 M$, NVDA −2,9 M$, BA +2,6 M$, DELL −2,4 M$, HYG +2,1 M$, SOXL +2,0 M$, XLU −1,9 M$,
  SOXX +1,7 M$, GOOGL +1,6 M$, SPY +1,5 M$, MSFT −1,3 M$, EWZ +1,2 M$, NKE +1,0 M$, TSLA −1,0 M$…
- `get_options_screener` : Unusually Bullish (STLA, STNE, ETHA, BAC, BIRK, MSTR, C, IOT, SOFI, XHB…),
  Unusually Bearish (KRE, HTZ, IWM, MAGS, NVDA, TTWO, OSCR, SPY, WMT, META, DDOG, MSFT…), Deep Conviction
  Calls (CCL, XHB, C, BHP, BE, DELL, SPY), Deep Conviction Puts (MSFT, CRWG, TLT, NVDA, DIA, AMD, NTRA).
- `get_dark_pool_trades` (≥ 5 M$) : AVGO 716 M$, MU 716 M$, ORCL 512 M$, INTC 475 + 306 + 220 M$, MRVL,
  QCOM, MSFT 300 M$, AMD 251 M$, CRM, WMT, AAPL, KO, PLTR…
- `get_open_interest_changes` : EWZ 43C/39C nov. (+149 k / +144 k), TLT 73P déc. (+76 k), HYG puts,
  IWM 268P/260P (+34 k / +23 k), KRE 60P nov. (+27 k), GOOGL 415C 09/10 (+26 k), SPY puts, XLU 41C…
- `get_insider_transactions` (P/S ≥ 200 k$, 14 j) : quasi exclusivement des ventes (XPO, BABA, KEYS, PG,
  VRSK, IOT, WDAY, UTHR…) ; un achat GME (254 k$). Aucun candidat concerné.
- `get_recent_congress_trades` : achats HD, AMGN, NFLX, GOOG, MSFT ; ventes MPC, STX, EMR, HD, DVN, GOOGL,
  ABBV, NEE… (petits montants).
- `get_market_seasonality` : octobre IWM +0,2 %, SPY +0,9 %, QQQ +1,3 %, XLF +1,0 %, XLK +1,5 %.

Présélection (prime nette × sources, univers 8–1 500 $, ≥ 2 Md$) et choix de 8 dossiers à enrichir :
**TLT, IWM, EWZ, NVDA, KRE, GOOGL, BA, CCL**. Écartés avant enrichissement : AMD (617 $), MSFT (513 $),
MU (1 096 $), DELL (548 $) — avec une NAV de 8,9 k$, un vertical delta 0,50/0,25 sur ces sous-jacents coûte
plusieurs centaines de dollars (> 3 % NAV) ; C et BAC (résultats les 13 et 14/10, aucune échéance
≥ 10 j avant) ; STLA (4,6 $ < 8 $) ; SOXL (ETF à levier) ; NKE (résultats la veille) ; INTC (résultats
le 22/10, direction mixte).

## 3. Enrichissement et scores

Indicateurs calculés sur 60 séances (`get_ticker_ohlc_latest_or_date`), murs gamma (`get_gex_levels`,
source vol), IV rank et prime nette de la veille (même flux), chaîne (`get_options_chain`, 1–2 échéances).

| Titre | Cours | SMA20 / SMA50 | ATR14 | IV rank | Prime nette 01/10 (bull − bear) | Murs put / call | Résultats | Direction | Score |
|---|---|---|---|---|---|---|---|---|---|
| TLT | 78,11 | 80,33 / 81,68 | 0,84 | 100 % | −38 M$ | 77 / 79 | — | baisse | **89** |
| IWM | 282,79 | 285,07 / 292,60 | 3,85 | 22 % | −20 M$ | 263 / 287 | — | baisse | **88** |
| EWZ | 37,75 | 37,59 / 36,33 | 0,75 | 98 % | −54 M$ (calls vendus) | 37 / 39 | — | hausse | **72** |
| NVDA | 235,46 | 223,86 / 218,31 | 5,03 | 0,4 % | −17 M$ | 222,5 / 232,5 | 18/11 | baisse | **71** |
| KRE | 70,69 | 72,18 / 74,34 | 1,26 | 28 % | −1,7 M$ | 69,5 / 70 | — | baisse | **71** |
| CCL | 25,78 | 22,94 / 25,27 | 0,96 | 22 % | +1,4 M$ | 24 / 26,5 | 18/12 | hausse | **68** |
| BA | 194,51 | 200,02 / 212,35 | 6,89 | 71 % | +0,7 M$ | 190 / 192,5 | 27/10 | hausse | **64** |
| GOOGL | 341,18 | 342,50 / 344,32 | 8,91 | 55 % | −50 M$ | 337,5 / 340 | 04/11 | baisse (faible) | 48 |

Détail des facteurs (poids × valeur) :

- **TLT** : flux −3,0, screener −0,75, prime jour −1,5, OI −1,0, tendance −1,5 ; qualité +0,4, gex +0,4,
  régime −0,08 → total 8,5.
- **IWM** : flux −3,0, screener −0,75, prime jour −1,5, OI −1,0, tendance −1,5 ; gex +0,4, saison −0,02,
  régime −0,08 → total 8,1.
- **EWZ** : flux +2,0, prime jour −1,5, OI +1,0, tendance +1,5 ; qualité +0,25, gex +0,4, régime +0,08 → 3,7.
- **NVDA** : flux −2,9, screener −1,5, prime jour −1,5, tendance +1,5 ; qualité +0,5, saison −0,17,
  régime (secteur Tech +0,60 contre la direction) −0,64, résultats −0,4 → 3,7.
- **KRE** : screener −0,75, prime jour −0,76, OI −0,65, tendance −1,5 ; régime −0,08 → 3,6.
- **CCL** : screener +0,75, prime jour +0,67, tendance +1,5 ; saison +0,01, régime +0,01 → 2,9.
- **BA** : flux +2,8, prime jour +0,35, tendance −1,5 ; qualité +0,18, gex +0,9, régime −0,06,
  résultats −0,4 → 2,3.
- **GOOGL** : flux +2,4, prime jour −1,5, OI +0,1, Congrès −0,17, tendance −1,5 ; qualité −0,25, gex −0,6,
  régime +0,33, résultats −0,4 → −0,2 (score 48 < 55).

## 4. Opportunités retenues (classées par EV / $ risqué)

| Titre | Sens | Structure | Qté | Limite | Plafond | TP | SL | Prime $ | Risque $ | Score | p | EV $ | Ids contrats IBKR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CCL | hausse | bull call spread 26/29 C 20/11/2026 (débit) | 2 | 1,04 | 1,12 | 2,11 | 0,52 | 208 | 114,4 | 67,7 | 0,542 | +63,6 (0,56 / $) | non vérifiés (IBKR à ré-authentifier) |
| KRE | baisse | bear put spread 70/69 P 20/11/2026 (débit, courte au mur gamma 69,5) | 5 | 0,46 | 0,50 | 0,75 | 0,23 | 230 | 126,5 | 71,1 | 0,551 | +23,1 (0,18 / $) | non vérifiés (IBKR à ré-authentifier) |

Conditions d'entrée et sorties : CCL action ≥ 25,92 (cours + 0,15 ATR), stop action 23,90 (sous le put wall
24), sortie temps 13/11 ; KRE action ≤ 70,50, stop action 72,58 (1,5 ATR), sortie temps 13/11.
Risque cumulé des deux tickets : 241 $ (2,7 % NAV).

Notes de construction :
- Les cotations UW datent de la clôture du 01/10 (CCL 25,07, KRE 69,95) alors que les sous-jacents cotent
  25,78 et 70,69 en pré-ouverture (+2,8 % et +1,1 %). Les mids ont été ajustés par delta/gamma
  (CCL 26/29 : 1,02 au lieu de 0,83 ; KRE 70/69 : 0,44 au lieu de 0,48) et les deltas de sélection
  recalculés au cours actuel. La re-cotation IBKR prévue à l'étape 6 n'a pas pu être faite.
- Pour KRE, l'échéance 30/10 (première valide dans le code) donnait avec le mur gamma 69,5 un spread
  70/69,5 de largeur 0,50 à EV négative ; l'échéance 20/11 (largeur 1,00) a été retenue, l'échéance
  étant libre dans la fenêtre 21–50 j et le classement se faisant par EV.
- Pour CCL, le 20/11 (EV/$ 0,56) a été préféré au 30/10 (26/28, EV/$ 0,54), quasi équivalents.

## 5. Candidats étudiés et écartés

| Titre | Score | Raison |
|---|---|---|
| TLT | 89 | IV rank 100 % → crédit (bear call 81/82 20/11, crédit ≈ 0,21) : EV négative. Avec TP = 50 % du crédit et SL = 2 × crédit (risque × 1,1), un crédit n'a une EV > 0 que si p > 0,69, or p ≤ 0,62 par construction : **tout spread crédit est écarté par la formule**. |
| IWM | 88 | Débit : bear put 280/≈270 (delta 0,50/0,25) ≈ 3,2 $ → prime 320 $ > 267 $ (3 % NAV). |
| EWZ | 72 | IV rank 98 % → crédit (bull put 33/32 20/11, crédit ≈ 0,25) : EV négative (même cause que TLT). Flux ambigu : 144 k calls 39 nov. traités au bid (ventes couvertes probables). |
| NVDA | 71 | Débit : bear put 230/220 (delta 0,50/0,25, mur 222,5 à 2,6 ATR hors fourchette) ≈ 3,6 $ → prime 365 $ > 267 $. Signal lui-même fragile : tendance et secteur haussiers, cours au-dessus du call wall, +2 % en pré-ouverture. |
| BA | 64 | IV rank 71 % → crédit bull put 185/175 23/10 : crédit 2,01 pour 10 de largeur → marge 802 $ et risque 218 $ > 178 $ ; EV négative de toute façon. |
| GOOGL | 48 | Score < 55 (flux haussier contre prime jour −50 M$ et tendance baissière) ; prime d'un vertical ≈ 600 $ de toute façon. |
| AMD, MSFT, MU, DELL | — | Non enrichis : sous-jacents > 500 $, vertical delta 0,50/0,25 hors budget prime. |
| C, BAC | — | Résultats les 13 et 14/10 : aucune échéance valide. |
| STLA, SOXL, NKE, INTC | — | Hors univers (prix < 8 $, ETF à levier), résultats la veille, résultats le 22/10 + direction mixte. |

## 6. Outils et flux utilisés

IBKR : `get_account_summary`, `get_account_positions`, `get_order_instructions` (OK, étape 0).
**Échec** : `search_contracts` (et donc `get_option_parameters`, `get_option_data`, `get_price_snapshot`,
`get_combo_identifier`) — « needs you to sign in again » : jeton du connecteur expiré en cours de run ;
l'étape 6 (vérification des jambes, bid/ask réels, identifiant de combo) n'a pas été réalisée. Aucune
instruction créée (run lecture seule).

Unusual Whales (OK) : `get_market_tide`, `get_market_etf_tide` (SPY, QQQ), `get_market_sector_tide` (4 secteurs),
`get_gex_levels` (SPY + 8 titres), `get_greek_exposure_by_ticker` (SPY), `get_market_events`,
`get_market_state`, `get_flow_alerts`, `get_options_screener` (4 presets), `get_dark_pool_trades`,
`get_open_interest_changes`, `get_insider_transactions`, `get_recent_congress_trades`,
`get_market_seasonality`, `get_ticker_ohlc_latest_or_date` (8 titres, 60 séances : SMA, ATR, IV rank,
primes), `get_options_chain` (13 appels), `get_short_data_by_ticker` (NVDA, CCL, BA), `get_analyst_ratings`
(4 titres), `get_average_return_per_month_by_ticker` (CCL, NVDA), `get_upcoming_earnings`.
Non appelés (économie d'appels ou sans valeur pour le score) : `get_company_info`,
`get_ticker_candles_by_range` (remplacé par l'historique journalier), `get_ticker_indicator_series`,
`get_greek_flow_by_ticker` (remplacé par les primes journalières), `get_flow_per_strike/expiry`,
`get_dark_pool_volume_price_group`, `get_max_pain`, `get_implied_volatility_term_structure` (IV rank déjà
fourni), `get_insider_activity_by_ticker` (renvoie la liste des initiés, pas les transactions),
`get_institutional_ownership_by_ticker`, `get_stock_screener`, `get_option_stance_ranking`,
`get_yield_curve`, `get_central_bank_rates`.

Limites rencontrées : `get_options_chain` ne renvoie **ni bid ni ask** (seulement theo / last / delta / OI /
volume), donc la règle de liquidité « spread ≤ max(0,10 ; 15 % du mid) » n'est vérifiable que via IBKR ;
plusieurs réponses (tides, OI, historique) dépassent la taille affichable et doivent être dépouillées en
fichier.

## 7. Points à corriger dans le skill

1. **Spreads crédit** : avec TP = 50 % du crédit, SL = 2 × crédit et risque × 1,1, l'EV est négative pour
   tout p ≤ 0,69, donc jamais positive avec p = 0,38 + 0,24 × score/100. Les candidats à IV rank ≥ 55 %
   (TLT, EWZ, BA aujourd'hui) sont systématiquement éliminés. Revoir TP/SL du crédit ou le calcul de p.
2. **Budget prime** : avec 8,9 k$ de NAV, la structure delta 0,50/0,25 n'est finançable que sur des
   sous-jacents < ~150 $ ; les titres les plus chauds (AMD, MSFT, MU, NVDA, IWM, GOOGL) sont éliminés.
   Prévoir une largeur réduite (strike court rapproché) quand la prime dépasse le budget.
3. **Mur gamma comme strike court** : à 0,8–0,9 ATR il produit des spreads de largeur 0,5–1 $ (KRE) ;
   imposer une largeur minimale (ex. ≥ 1 ATR) ou revenir au delta 0,25.
4. **Risk-off** : `events_within` marque risk-off pour tout événement du calendrier (Factory Orders inclus) ;
   préciser la liste (FOMC, CPI, NFP, PCE…) ou un niveau d'importance.
5. **Pré-ouverture** : les chaînes UW sont de la veille alors que les sous-jacents ont bougé ; la re-cotation
   IBKR est indispensable (ou décaler le run après 09:45).
6. `get_insider_activity_by_ticker` ne fournit pas de transactions : utiliser `get_insider_transactions`
   avec `ticker_symbol`. `get_short_data_by_ticker` donne le taux d'emprunt, pas le short interest %.
