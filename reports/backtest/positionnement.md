# Positionnement et événements : jeu de données point-in-time

Fichier : `positionnement.csv`, 830 lignes = 136 lignes du panel `calibration-signaux.csv` + 694 lignes de `panel_screener.csv` (union sans doublon sur date,ticker).

## Couverture (panel de base 136 / total 830)

| Colonne | Base | Total | Source et méthode |
|---|---|---|---|
| dp_premium_d | 136 | 830 | Volume hors bourse FINRA (TRF/ADF) du jour D × VWAP de D (Massive `short-volume` + agrégats journaliers) |
| dp_vs_adv | 136 | 830 | dp_premium_d / moyenne des 20 dernières séances (D incluse) de volume × VWAP |
| oi_call_prem_d, oi_put_prem_d | 0 | 0 | **Non disponible** (voir plus bas) |
| insider_buy_30d / sell_30d | 88 | 526 | Formulaires 4 SEC, codes P/S, titres non dérivés, **date de dépôt** dans [D−30, D]. Vide pour les ETF et les émetteurs sans formulaire 4 (ASML, SKHY…) |
| congress_buys/sells_60d | 136 | 830 | UW `politics_flow`, **date de publication** (`filed_at_date`) dans [D−60, D] |
| analyst_up/down_30d | 94 | 578 | UW `analyst_ratings`, relèvements et abaissements dans [D−30, D]. Vide pour les ETF |
| short_vol_ratio_5d | 136 | 830 | Moyenne FINRA du ratio short volume / volume sur les 5 séances jusqu'à D |
| days_to_earnings, earnings_within_7 | 92 | 563 | Séances ouvrées entre D et la prochaine publication ≥ D (UW `upcoming_earnings` : dernière et prochaine date). within_7 = 1 si ≤ 7 séances. Exclus : ETF, SKHY, BMNR, SBSW et FPS (données périmées) |
| season_avg_month, season_win_month | 116 | 239 | UW `average_return_per_month`, pour le mois de D. Vide si l'historique compte moins de 5 ans, ainsi que pour AAOI et SPCX (artefacts à −100 %). Non récupéré pour les tickers présents uniquement dans le screener |

## Écarts par rapport au cahier des charges
- **Dark pool** : `get_dark_pool_trades` renvoie au plus 50 transactions par appel. Pour sommer une journée sur de gros titres, il aurait fallu des centaines de pages. J'ai donc utilisé le volume hors bourse FINRA quotidien, qui est un indicateur proche mais plus large : il inclut l'internalisation des courtiers, pas seulement les ATS. Il est publié le soir de D. Le ratio peut dépasser 1 sur les titres peu liquides (DPRO, LITE, DLLL).
- **OI changes** : `get_open_interest_changes` n'accepte pas de paramètre de date et ne renvoie que la dernière séance (2 octobre). Aucune valeur historique n'est accessible. Les deux colonnes sont donc laissées vides, sans approximation.
- Les données d'initiés et les notes d'analystes viennent de Massive (formulaire 4) et de UW (deux requêtes à l'échelle du marché, filtrées ensuite en Python). Les autres données viennent de UW.

## Risques de look-ahead
1. **Saisonnalité** : les statistiques sont calculées aujourd'hui et incluent août et septembre 2026, soit les mois mêmes du test. Sur 19 ans, le poids de 2026 est d'environ 5 %. Il devient important pour les historiques courts, d'où l'exclusion sous 5 ans.
2. **Dates de résultats** : la date est celle connue au 2 octobre. La date future (novembre) est souvent marquée « estimation ». À la date D, une date annoncée plus tard ou modifiée a pu différer.
3. **Notes d'analystes** : filtrage sur la date calendaire UTC de D. Une note publiée après la clôture de D est comptée, ce qui crée un léger biais en faveur de D.
4. **FINRA** (short volume et hors bourse de D) : publié vers 18 h ET le jour D, donc disponible pour une exécution le matin de D+1 mais pas pendant la séance de D.
5. **Formulaire 4 et Congrès** : on filtre sur la date de dépôt ou de publication, donc pas de fuite. L'horodatage intrajournalier n'est pas vérifié pour un dépôt le jour D.
6. Les dates de résultats « dernière/prochaine » supposent au plus une publication entre D et le 2 octobre, ce qui est vrai sur la fenêtre testée.
