# Test rétroactif des filtres du Desk Flow sur les tickets du Desk Swing Options (clôture du 30/09/2026)

Point dans le temps : fin de séance du 30/09/2026 (tickets pour l'ouverture du 01/10). Sources : Unusual Whales (`get_gex_levels` source OI, `get_stock_screener`, `get_greek_exposure_by_ticker`, clôtures quotidiennes `get_ticker_ohlc_latest_or_date`) et IBKR en lecture seule (`get_account_trades` DAYS_7, `get_account_positions`).

Méthode :
- Murs gamma : facteur = tanh(place) − 0,5·tanh(appui), distances en ATR14 plafonnées à 5 (identique à `scanner/scoring.py::facteur_gex`). VETO (« murs contre ») si facteur < −0,05.
- Gamma des dealers : call_gamma + put_gamma au 30/09. « Setup gamma » = facteur > 0 et gamma net < 0.
- Ratio IV/HAR : `scanner.volatilite.ratio_iv(iv30d du 30/09, 78 clôtures jusqu'au 30/09 inclus)`. « Cher » si > 1,2. Pour les spreads crédit, le filtre de vol n'a pas été validé (le Desk Flow ne l'a validé que sur les spreads débit) : ratio donné pour information.
- Mouvement : (dernier cours 02/10 vers 13h NY − clôture 30/09) / ATR14, signé dans le sens du trade (positif = favorable). Environ 1,5 séance, pas l'horizon de 7 séances.

| Ticker | Sens | Structure | Murs gamma (clôture → call / put wall ; facteur) | Gamma dealers (net 30/09) | Verdict gamma | Ratio IV/HAR | Mouvement depuis 30/09 (ATR) | Trade réel et P&L |
|---|---|---|---|---|---|---|---|---|
| UPS | baissier | spread crédit call | 93,44 → 110 / aucun put wall ; facteur non calculable (0) | −0,12 M (négatif) | neutre (pas de put wall, le code renvoie 0) | 1,46 (cher, non validé crédit) | −0,05 | non tradé |
| LVS | baissier | spread crédit call | 37,83 → 40 / 30 ; +0,51 | +0,10 M (positif) | neutre | 1,97 (cher, non validé crédit) | +1,26 | non tradé |
| NEE | baissier | spread crédit call | 75,78 → 76 / 40 ; +0,91 | −0,31 M (négatif) | setup gamma | 2,03 (cher, non validé crédit) | −1,00 | 77/79 C 23/10 : ouvert 01/10 crédit 0,59 (V 77C 1,19 / A 79C 0,60), clôturé 02/10 débit 0,92 (A 77C 2,05 / V 79C 1,13) → −33 $ brut, −36,46 $ net |
| SMCI | haussier | spread débit call | 41,08 → 43,5 / 40 ; +0,56 | +1,72 M (positif) | neutre | 1,50 (cher) | +1,01 | 39/47 C 30/10 : ouvert 01/10 débit 3,18 (A 39C 4,71 / V 47C 1,53), clôturé 02/10 crédit 3,74 (V 39C 5,63 / A 47C 1,89) → +56 $ brut, +52,51 $ net |
| ASST | haussier | spread débit call | 29,43 → 30 / 27 ; −0,13 | +2,03 M (positif) | **VETO** (murs contre) | 1,75 (cher) | +0,42 | non tradé |
| ASX | haussier | spread crédit put | 44,47 → 47,5 / 42,5 ; +0,54 | +0,20 M (positif) | neutre | 1,42 (cher, non validé crédit) | +1,82 | 42,5/37,5 P 16/10 : ouvert 01/10 crédit 0,90 (V 42,5P 1,65 / A 37,5P 0,75), clôturé 02/10 débit 0,44 (A 42,5P 0,51 / V 37,5P 0,07) → +46 $ brut, +43,96 $ net |
| ARKK | haussier | spread crédit put | 89,05 → 95 / 83 ; +0,50 | +0,09 M (positif) | neutre | 1,58 (cher, non validé crédit) | +0,33 | non tradé |
| NCLH | baissier | spread débit put | 14,66 → 15,5 / 14,5 ; −0,18 | +0,15 M (positif) | **VETO** (murs contre) | 1,76 (cher) | −0,59 | non tradé |
| OKLO | baissier | spread débit put | 37,08 → 45 / 31,5 ; +0,49 | +0,25 M (positif) | neutre | 1,55 (cher) | +0,34 | non tradé |
| NVO | baissier | put long | 37,92 → 50 / 25 ; +0,50 | −1,01 M (négatif) | setup gamma | 1,12 (correct) | +0,57 | non tradé |

Trades réels (IBKR, 7 derniers jours) : seuls NEE, SMCI et ASX parmi les 10 tickers ; 1 contrat chacun, tous ouverts le 01/10 et clôturés le 02/10 vers 15h25 UTC, plus aucune position ouverte. P&L net cumulé (commissions incluses, `realized_pnl` IBKR) : **+60,01 $** (brut +69 $). Les correspondances jambe ↔ strike sont déduites des prix (la jambe la plus proche de la monnaie est la plus chère). Les autres exécutions de la période (CCL, CRWV, KRE, ETHA, TGT, TTD, XSP) ne concernent pas ces tickets.

## Lecture

- Échantillon minuscule (10 tickets, 3 trades réels) et 1,5 séance seulement au lieu de 7 : aucune conclusion statistique possible, c'est une vérification de cohérence.
- Le veto aurait écarté 2 tickets (ASST et NCLH, deux spreads débit, non tradés). À ce stade NCLH va contre le trade (−0,59 ATR) — le veto aurait évité une perte latente — mais ASST va dans le bon sens (+0,42 ATR) : 1 pour 1.
- Aucun des trois trades réellement exécutés n'aurait été bloqué par le veto. Le seul « setup gamma » tradé, NEE, est le seul perdant (−1,0 ATR contre la position) : le cours était collé au call wall 76 (0,18 ATR) traité comme appui en sens baissier, et il l'a franchi ; c'est le cas limite où un mur proche « derrière » cède.
- Le filtre de vol aurait classé presque tout « cher » (9/10 au‑dessus de 1,2, seul NVO à 1,12) : sur ce jour il ne discrimine rien, et pour les 6 spreads crédit il n'a de toute façon pas été validé.
- En résumé : le veto du Desk Flow n'aurait changé ni le P&L réalisé (+60 $ net) ni la sélection des trades exécutés ; il aurait seulement retiré deux tickets non tradés au résultat partagé à ce stade.
