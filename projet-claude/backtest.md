# Backtest croisé du Desk Flow

## Conclusions (2 octobre 2026)

- **Aucune source seule ne bat le hasard** sur 830 signaux : flux d'options, screeners, prime nette du jour,
  tendance, momentum, régime de marché, initiés, analystes, dark pool. Le score d'origine du desk n'était pas
  monotone : ses notes au-dessus de 75 faisaient le moins bien.
- **Les murs gamma sont le seul facteur robuste.** Quand le trade bute sur un mur, l'action ne fait 1 ATR dans le
  bon sens que 9 à 15 % du temps, sur chaque moitié de la période et sur chaque panel. Ces trades sont rejetés.
- **Setup gamma** (murs favorables et gamma des dealers négatif) : 33 % de réussite à 1 ATR contre 26 % au hasard,
  repéré sur le panel flux et confirmé sur le panel screener (32,6 %, n = 46). Sur 84 trades, un spread simulé
  gagne +2,9 % de la prime en moyenne si l'exécution coûte 1,5 % de la largeur par sens, avec une erreur type de
  4,8 % : **prometteur, pas prouvé**. À 5 % de coût par sens, il perd 10 à 15 %.
- **L'exécution décide de tout** : entrée au mid, spreads dont l'écart achat-vente cumulé reste sous 3 % de la
  largeur, aucune poursuite du prix.
- Limites : deux mois d'un marché plat, signaux corrélés au sein d'une séance, prix d'options simulés
  (Black-Scholes à l'IV du jour), variations d'open interest non testables à date, saisonnalité biaisée,
  certains cours et données d'initiés obtenus hors Unusual Whales pour le seul besoin du backtest.

## Détail

830 signaux (136 flux, 694 screener seul), 17 séances (2026-08-06 → 2026-09-22), issue à 7 séances. Hasard au seuil 1 ATR : 0.259.

## Facteurs un par un (gain = mouvement ≥ 1 ATR dans le sens du signal)

| Facteur | Couverture | n confirme | gain | IC 95 % | mvt moyen (ATR) | n contredit | gain | mvt moyen | écart |
|---|---|---|---|---|---|---|---|---|---|
| murs_gamma | 317 | 253 | 0.281 | 0.23–0.34 | +0.06 | 44 | 0.091 | -0.60 | +0.190 |
| congres | 830 | 168 | 0.333 | 0.27–0.41 | +0.35 | 173 | 0.173 | -0.28 | +0.160 |
| saisonnalite | 239 | 113 | 0.363 | 0.28–0.46 | +0.51 | 99 | 0.222 | -0.34 | +0.141 |
| gamma_negatif | 340 | 101 | 0.327 | 0.24–0.42 | +0.27 | 239 | 0.234 | -0.13 | +0.092 |
| liquidite_os | 830 | 781 | 0.275 | 0.24–0.31 | +0.07 | 42 | 0.214 | -0.38 | +0.061 |
| rsi_extreme | 830 | 350 | 0.277 | 0.23–0.33 | +0.05 | 333 | 0.243 | -0.10 | +0.034 |
| spy_gamma_positif | 830 | 254 | 0.280 | 0.23–0.34 | +0.25 | 576 | 0.269 | -0.04 | +0.010 |
| attraction_max_pain | 340 | 161 | 0.261 | 0.20–0.33 | +0.13 | 172 | 0.267 | -0.12 | -0.007 |
| short_volume | 830 | 357 | 0.266 | 0.22–0.31 | -0.01 | 414 | 0.273 | +0.11 | -0.007 |
| tendance | 817 | 304 | 0.250 | 0.20–0.30 | -0.05 | 332 | 0.262 | +0.00 | -0.012 |
| au_dessus_flip | 326 | 176 | 0.244 | 0.19–0.31 | -0.10 | 150 | 0.267 | -0.01 | -0.022 |
| analystes | 578 | 55 | 0.200 | 0.12–0.32 | -0.03 | 47 | 0.234 | -0.45 | -0.034 |
| momentum_5j | 830 | 444 | 0.259 | 0.22–0.30 | -0.05 | 355 | 0.299 | +0.19 | -0.040 |
| iv_rank_bas | 830 | 644 | 0.278 | 0.24–0.31 | +0.04 | 88 | 0.318 | +0.24 | -0.040 |
| screener | 756 | 731 | 0.276 | 0.24–0.31 | +0.07 | 25 | 0.320 | +0.04 | -0.044 |
| prime_nette_jour | 830 | 564 | 0.261 | 0.23–0.30 | +0.03 | 229 | 0.323 | +0.18 | -0.063 |
| inities | 526 | 137 | 0.285 | 0.22–0.36 | +0.14 | 156 | 0.353 | +0.24 | -0.068 |
| regime_marche | 830 | 411 | 0.226 | 0.19–0.27 | -0.14 | 419 | 0.317 | +0.24 | -0.091 |
| regime_secteur | 94 | 50 | 0.160 | 0.08–0.28 | -0.50 | 41 | 0.317 | +0.70 | -0.157 |
| dark_pool | 830 | 830 | 0.272 | 0.24–0.30 | +0.05 | 0 | nan | +nan | +nan |
| etf | 830 | 0 | nan | 0.00–1.00 | +nan | 252 | 0.274 | +0.01 | +nan |
| flux | 136 | 136 | 0.243 | 0.18–0.32 | -0.05 | 0 | nan | +nan | +nan |
| macro_lendemain | 830 | 0 | nan | 0.00–1.00 | +nan | 231 | 0.303 | +0.29 | +nan |
| mega_cap | 830 | 0 | nan | 0.00–1.00 | +nan | 129 | 0.279 | +0.15 | +nan |
| open_interest | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| resultats_7j | 563 | 0 | nan | 0.00–1.00 | +nan | 52 | 0.481 | +0.39 | +nan |

## Score du desk actuel (dans le sens du signal)

| Score | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|
| 0–45 | 119 | 0.277 | 0.20–0.36 | -0.14 |
| 45–55 | 181 | 0.260 | 0.20–0.33 | +0.06 |
| 55–65 | 318 | 0.277 | 0.23–0.33 | +0.09 |
| 65–75 | 139 | 0.273 | 0.21–0.35 | +0.02 |
| 75–101 | 73 | 0.274 | 0.18–0.39 | +0.22 |

## Score appris (dates < 2026-08-28) puis testé (dates ≥ 2026-08-28)

Facteurs retenus sur la première moitié : congres, liquidite_os, murs_gamma, saisonnalite, screener.

| Échantillon | Votes nets | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|---|
| apprentissage | < 0 | 13 | 0.154 | 0.04–0.42 | -0.13 |
| apprentissage | 0 | 24 | 0.167 | 0.07–0.36 | -0.41 |
| apprentissage | 1 | 66 | 0.197 | 0.12–0.31 | -0.02 |
| apprentissage | ≥2 | 291 | 0.320 | 0.27–0.38 | +0.45 |
| test | < 0 | 13 | 0.154 | 0.04–0.42 | -1.21 |
| test | 0 | 30 | 0.300 | 0.17–0.48 | -0.33 |
| test | 1 | 76 | 0.145 | 0.08–0.24 | -0.49 |
| test | ≥2 | 317 | 0.290 | 0.24–0.34 | -0.04 |

## Filtre gamma : repéré sur le panel flux, testé sur le panel screener

Règle : murs gamma favorables (> 0) ET gamma des dealers négatif.

| Panel | Règle | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|---|
| flux (découverte) | vérifiée | 38 | 0.342 | 0.21–0.50 | +0.21 |
| flux (découverte) | murs seuls > 0 | 103 | 0.291 | 0.21–0.39 | +0.02 |
| flux (découverte) | non vérifiée | 94 | 0.191 | 0.12–0.28 | -0.26 |
| flux (découverte) | tous | 132 | 0.235 | 0.17–0.31 | -0.13 |
| screener (test) | vérifiée | 46 | 0.326 | 0.21–0.47 | +0.45 |
| screener (test) | murs seuls > 0 | 159 | 0.270 | 0.21–0.34 | +0.07 |
| screener (test) | non vérifiée | 139 | 0.237 | 0.17–0.32 | -0.15 |
| screener (test) | tous | 185 | 0.259 | 0.20–0.33 | +0.00 |

## Spreads simulés

Rendement simulé d'un spread acheté, en multiple de la prime payée.

| Groupe | n | rendement moyen | médiane | trades gagnants |
|---|---|---|---|---|
| tous les signaux | 829 | -21.3% | -23.1% | 29% |
| flux seul | 135 | -23.5% | -27.9% | 25% |
| screener seul | 694 | -20.9% | -22.9% | 30% |
| règle gamma vérifiée, panel flux | 38 | -15.4% | -16.2% | 29% |
| règle gamma vérifiée, panel screener (test) | 46 | -10.2% | -17.3% | 35% |
| murs gamma contre le trade | 44 | -36.3% | -33.9% | 11% |
| score du desk ≥ 65 | 211 | -19.9% | -23.3% | 29% |
| score appris ≥ 2, dates de test | 317 | -22.9% | -24.4% | 31% |

Lecture : un facteur utile a un « gain » nettement plus haut quand il confirme que quand il contredit, et un mouvement moyen positif quand il confirme. Avec moins de 300 signaux sur deux mois, un écart de moins de 10 points n'est pas distinguable du bruit.
