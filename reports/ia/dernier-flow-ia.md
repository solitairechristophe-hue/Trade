# Desk Flow (connecteurs) — 2026-10-02 12:40 New York

Troisième run du jour, **premier avec les nouvelles règles** (SKILL.md §4–5 réécrits après le backtest du 2 octobre :
portes gamma, entrée au mid, écart achat-vente cumulé ≤ 3 % de la largeur, taille d'essai 1 combo, EV = rendement
mesuré du setup gamma +2,9 % de la prime). Mode horaire, marché ouvert. IBKR en **lecture seule** : aucune
instruction d'ordre, aucune alerte créée. Rien n'a été commité ni poussé.

## 0. Compte IBKR (lecture seule)

- `get_account_summary` : NAV (net liquidation) **8 853,42 $** (≈ 8 914 annoncé ; budget par trade : risque ≤ 177 $, prime ≤ 265,6 $).
- `get_account_positions` : **aucune position ouverte** (toutes les lignes à 0). `get_order_instructions` : aucune.
- `get_account_trades` (aujourd'hui) — **à lire avant toute chose** :
  - les trois tickets du matin ont été **exécutés puis clôturés** : CCL 26/29 C (achat 10:14 NY à 0,92 net, revente 11:23 à 0,87),
    KRE 70/69 P (achat 10:17 à 0,39 net, revente 11:23 à 0,38), CRWV 93/100 C (achat 10:31 à 2,44 net, revente 11:24 à 2,16) ;
  - ASX, NEE, SMCI et ETHA ont aussi été soldés entre 11:23 et 11:25 NY (liquidation groupée).
  - Conséquences : ASX, NEE, SMCI, ETHA, CCL, KRE, CRWV exclus (un trade par titre et par jour). Le compteur
    « 3 ordres / jour » du robot peut déjà être consommé par ces trois entrées : à vérifier côté VPS avant de compter
    sur l'envoi automatique du ticket IWM.

## 1. Partie A — revue des 3 tickets du jour contre les portes gamma

Données live : `get_gex_levels` (source vol, 16:38 UTC), `get_greek_exposure_by_ticker` (dernière ligne, gamma net
dealers = call_gamma + put_gamma), ATR14 recalculé sur 15 séances (`get_ticker_ohlc_latest_or_date`, méthode
`scanner/uw_client.py`), cotations des jambes `get_price_snapshot` IBKR (12:29–12:39 NY).
Facteur = tanh(place) − 0,5 × tanh(appui), distances en ATR plafonnées à 5 (`scanner/scoring.py`).

| Ticket | Sens | Cours | ATR14 | Put wall / call wall | Place / appui (ATR) | **Facteur murs** | **Gamma net dealers** | Jambes IBKR (bid/ask) | **Écart cumulé / largeur** | **Décision** |
|---|---|---|---|---|---|---|---|---|---|---|
| CCL 26/29 C 20/11 | hausse | 25,62 | 0,951 | 24,5 / 26 | 0,40 / 1,18 | **−0,031** | **+0,87 M** (positif) | 26C 1,25/1,33 ; 29C 0,39/0,45 → mid 0,87 | 0,14 / 3 = **4,7 %** | **REJET** — pas de setup gamma (murs ≤ 0, gamma positif), écart > 3 % |
| KRE 70/69 P 20/11 | baisse | 70,44 | 1,308 | 60 / 73 | 5,00 (8,0 réel) / 1,96 | **+0,519** | **−1,89 M** (négatif) | 70P 2,21/2,42 ; 69P 1,84/2,03 → mid 0,38 | 0,40 / 1 = **40 %** | **REJET** — setup gamma valide, mais liquidité : écart 13 × le maximum |
| CRWV 93/100 C 30/10 | hausse | 89,60 | 4,421 | 80 / 91 | 0,32 / 2,17 | **−0,181** | **+0,95 M** (positif) | 93C 5,45/5,70 ; 100C 3,35/3,50 → mid 2,175 | 0,40 / 7 = **5,7 %** | **REJET** — murs contre le trade (< −0,05) |

KRE : aucune restructuration ne passe la règle des 3 % (écarts de 0,19–0,21 par jambe ; il faudrait une largeur ≥ 13 $,
soit 10 ATR et une prime hors budget). Les trois places du quota sont libérées.

Identifiants IBKR des jambes revues : CCL 26C 881655384, 29C 881655564 ; KRE 70P 853207255, 69P 853207241 ;
CRWV 93C 922385799, 100C 922384816.

## 2. Régime de marché

| Flux | Lecture 12:35 NY |
|---|---|
| Market tide | net call +130,4 M$, net put −48,8 M$ → niveau call − put **+179,2 M$** ; il y a une heure (11:35) +167,1 M$ → pente **+12,2 M$** |
| **Biais** | 0,6 × tanh(12,2/50) + 0,4 × tanh(179,2/150) = 0,6 × 0,24 + 0,4 × 0,83 = **+0,48 (haussier modéré)** — en net repli depuis le pic de 10:25 (+300 M$) |
| SPY gamma | call 3,90 M / put −3,79 M → **+0,11 M (quasi neutre, légèrement positif)** ; put wall 768, flip 769,07, call wall 787 ; SPY ≈ 768,9, collé au put wall / flip |
| Événements | Emploi (08:30) et Factory Orders (10:00) publiés ; rien de majeur dans les 2 h → **pas de risk-off** |

## 3. Partie B — découverte (flux depuis 11:10 NY) et porte gamma d'abord

`get_flow_alerts` (newer_than 11:10 NY, ≥ 50 k$, 5–90 DTE, Common Stock/ADR/ETF, tri prime, 50 alertes) — prime nette
(ask − bid, calls + / puts −) : NVDA −7,2 M$, AMDL −4,7 (levier, exclu), IWM −2,7, ACN +2,6, SOXX +2,1 (puts vendus),
QQQ +2,0, MDB −1,9, VIAV −1,3, SOXL −1,2 (levier), XBI −1,1, GLD −1,1, MPWR −0,8, NTAP +0,7, CRM +0,6, SNOW +0,5…
`get_options_screener` : Unusually Bullish (SPCX 172,5C 30/10 6,5 M$, CRWV 103C, PBR, FCX, BA, AAPL, CDNS, MXL…) ;
Unusually Bearish (BAC 53P, INTC 120P, SMCI, CRWV 77P, MU, CRWD 265P 20/11 2,8 M$ floor, META, LITE, TMO, GOOGL…).

Les 10 plus chauds (prime nette × sources), porte gamma calculée **avant** tout enrichissement :

| Titre | Sens | Cours | Put / call wall | ATR14 | Facteur murs | Gamma net dealers | Porte |
|---|---|---|---|---|---|---|---|
| NVDA | baisse | 235,49 | 225 / 240 | ≈ 4,7* | +0,61* | +4,87 M | **échoue** (gamma positif) |
| **IWM** | baisse | 281,50 | 268 / 284 | **3,826** | **+0,711** (place 3,53, appui 0,65) | **−4,54 M** | **PASSE** |
| ACN | hausse | 204,23 | 197,5 / 210 | ≈ 4,1* | +0,42* | +0,02 M | échoue (gamma positif) |
| SOXX | hausse | 594,26 | 585 / 605 | ≈ 11,9* | +0,39* | +0,03 M | échoue (gamma positif) |
| QQQ | hausse | 749,28 | 740 / 752 | ≈ 15,0* | −0,10* | +0,98 M | échoue (murs contre, gamma positif) |
| MDB | baisse | 356,96 | 352,5 / 365 | ≈ 7,1* | +0,15* | +0,02 M | échoue (gamma positif) |
| SPCX | hausse | 157,56 | 143 / 170 | ≈ 3,2* | +0,50* | +0,05 M | échoue (gamma positif) |
| CRWD | baisse | 269,33 | 265 / 270 | ≈ 5,4* | +0,60* | +0,13 M | échoue (gamma positif) |
| **XBI** | baisse | 154,57 | 133 / 159 | **4,226** | **+0,609** (place 5,0, appui 1,05) | **−0,28 M** | **PASSE** |
| GLD | hausse/baisse | 379,90 | 379 / 381 | ≈ 7,6* | +0,05* | +0,02 M | échoue (gamma positif) |

\* ATR non téléchargé (gamma positif suffit à rejeter) : repli du code `price × 2 %`, facteur indicatif.

**2 candidats sur 10 passent la porte gamma : IWM et XBI.**

### Structuration des deux setups (débit, IV rank < 55 %)

- **IWM** (IV rank 16 %, pas de résultats) : échéance 23/10 (21 j) retenue — longue 282 P (delta −0,51), courte 274 P
  (delta ≈ −0,26, 2,0 ATR) ; largeur 8 = 2,09 ATR. IBKR : 282P 4,74/4,79, 274P 2,13/2,17 → **mid 2,615**, écart cumulé
  0,09 = **1,1 %** de la largeur ✓. Prime 262 $ ≤ 265,6 $ ✓. Gain/risque 2,05 (282/275 : 1,93 ; 30/10 282/274 ≈ 2,80 $
  hors budget, 282/277 30/10 : 1,65). Score de confluence estimé ≈ 85–90 (murs 3 × 0,71, gamma 1,5, flux baissier,
  prime du jour −6,4 M$, régime −0,24) ≥ 55.
- **XBI** (IV rank 36 %) : **rejeté pour liquidité**. 23/10 : 155P 3,40/5,00, 154P 3,20/4,50, 150P 2,31/2,80, 149P 1,73/2,49 ;
  20/11 : 155P 6,70/7,35, 150P 4,35/5,10, 145P 2,99/3,40 → écart cumulé 1,06 sur 10 $ = 10,6 % (et prime 3,83 $ hors budget).

## 4. Trade retenu (1 sur 3 places libres)

| Titre | Sens | Structure | Qté | Limite (= mid) | Plafond | TP | SL | Prime $ | Risque $ | EV $ (setup gamma) | EV / $ risqué |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **IWM** | baisse | bear put 282/274 P 23/10/2026 (débit) | 1 | 2,62 | 2,62 | 5,04 | 1,31 | 262 | 144,1 | **+7,6** (0,029 × 262, erreur type ±12,6) | 0,05 |

Ticket : `tickets/2026-10-02-flow-ia.json` (id `flow-ia-2026-10-02-IWM`), validé par `executor` (aucune erreur,
aucun refus à NAV 8 914 et 8 853). EV positive mais « non prouvée » (moins d'une erreur type au-dessus de zéro) : taille
d'essai 1 combo, à journaliser.

### Ordre à poser dans TWS — IWM

1. **Combo** : IWM, échéance 23 oct. 2026 — **ACHAT 1 × 282 Put**, **VENTE 1 × 274 Put** ; quantité **1** ; côté **BUY** (débit).
   Combo IBKR `0;;;920239671/1,920695595/-1` (« IWM Oct23 274/282 Bear Put »).
2. **Entrée** : **LIMIT 2,62, TIF DAY** (mid IBKR à 12:40 ; ne pas poursuivre le prix).
3. **Condition** : prix de IWM **≤ 280,75** (cours 281,32 − 0,15 ATR), déclenchement « Last », hors séance **décoché**.
4. **Take profit** : Profit Taker LIMIT **GTC à 5,04**.
5. **Stop sur l'action** : clôture de IWM **≥ 287,06** (1,5 ATR ; call wall à 284) → fermer le combo (SL combo de référence 1,31).
6. **Sortie temps** : **lundi 12 oct. 2026**, fermer quoi qu'il arrive (échéance − 7 j = 16/10, plus tard).

Identifiants IBKR : IWM (sous-jacent) 9579970 ; 282 P 23/10 **920239671** ; 274 P 23/10 **920695595**.

## 5. Titres exclus et raisons

| Titre | Raison |
|---|---|
| CCL, KRE, CRWV | Tickets du matin rejetés (§1) ; déjà tradés et clôturés aujourd'hui |
| ASX, NEE, SMCI, ETHA | Positions du jour (soldées à 11:23–11:25) — un trade par titre |
| NVDA, ACN, SOXX, MDB, SPCX, CRWD, GLD | Gamma net des dealers positif → pas de setup gamma |
| QQQ | Murs contre le trade (call wall 752 à 0,2 ATR) et gamma positif |
| XBI | Setup gamma valide, mais écart achat-vente cumulé 10,6 % de la largeur (> 3 %), prime hors budget |
| AMDL, SOXL | ETF à levier |
| AAPL, BA, CDNS, FCX, MXL, GLW, PM, STX, INTC, BAC, TMO, TXN | Résultats du 14 au 29/10 : aucune échéance 21–50 j valide (et non classés dans les 10) |

## 6. Outils utilisés et limites

IBKR (lecture seule) : `get_account_summary`, `get_account_positions`, `get_order_instructions`, `get_account_trades`,
`search_contracts` (IWM, XBI), `get_option_parameters`, `get_option_data`, `get_price_snapshot` (13 jambes + 2 sous-jacents),
`get_combo_identifier` (IWM). Aucune instruction ni alerte créée.
Unusual Whales : `get_market_tide`, `get_gex_levels` (SPY + 13 titres), `get_greek_exposure_by_ticker` (SPY + 13 titres),
`get_market_events`, `get_flow_alerts`, `get_options_screener` (2 presets), `get_ticker_ohlc_latest_or_date` (CCL, KRE, CRWV,
IWM, XBI), `get_options_chain` (IWM 23/10 et 30/10).
Non appelés (économie, aucun dossier hors setup gamma à enrichir) : dark pool, OI, initiés, Congrès, presets Deep
Conviction, secteurs, enrichissement complet §3. L'ATR inclut la bougie du jour en cours (comme le scanner).


## Mise à jour après la porte de volatilité (même jour)

Le ticket IWM est **retiré**. Son option est trop chère pour la règle ajoutée après la revue de littérature :

| Mesure | Valeur |
|---|---|
| IV 30 jours (Unusual Whales) | 18,9 % |
| Volatilité prévue HAR (clôtures jusqu'au 1er octobre) | 9,0 % |
| Volatilité réalisée selon Unusual Whales | 11,2 % |
| Ratio IV / volatilité prévue | 1,6 à 2,1, plafond 1,2 |

En backtest, le setup gamma avec une option chère (ratio > 1,3) perdait 12 % de la prime en moyenne.
**Aucun trade ne passe toutes les portes aujourd'hui.**
