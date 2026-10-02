# Backtest croisé du Desk Flow

830 signaux (136 flux, 694 screener seul), 17 séances (2026-08-06 → 2026-09-22), issue à 7 séances. Hasard au seuil 1 ATR : 0.259.

## Facteurs un par un (gain = mouvement ≥ 1 ATR dans le sens du signal)

| Facteur | Couverture | n confirme | gain | IC 95 % | mvt moyen (ATR) | n contredit | gain | mvt moyen | écart |
|---|---|---|---|---|---|---|---|---|---|
| murs_gamma | 132 | 98 | 0.296 | 0.21–0.39 | +0.04 | 24 | 0.042 | -0.65 | +0.254 |
| gamma_negatif | 136 | 42 | 0.333 | 0.21–0.48 | +0.39 | 94 | 0.202 | -0.24 | +0.131 |
| liquidite_os | 830 | 781 | 0.275 | 0.24–0.31 | +0.07 | 42 | 0.214 | -0.38 | +0.061 |
| rsi_extreme | 830 | 350 | 0.277 | 0.23–0.33 | +0.05 | 333 | 0.243 | -0.10 | +0.034 |
| attraction_max_pain | 136 | 66 | 0.258 | 0.17–0.37 | +0.14 | 67 | 0.224 | -0.24 | +0.034 |
| spy_gamma_positif | 830 | 254 | 0.280 | 0.23–0.34 | +0.25 | 576 | 0.269 | -0.04 | +0.010 |
| tendance | 817 | 304 | 0.250 | 0.20–0.30 | -0.05 | 332 | 0.262 | +0.00 | -0.012 |
| momentum_5j | 830 | 444 | 0.259 | 0.22–0.30 | -0.05 | 355 | 0.299 | +0.19 | -0.040 |
| iv_rank_bas | 830 | 644 | 0.278 | 0.24–0.31 | +0.04 | 88 | 0.318 | +0.24 | -0.040 |
| screener | 756 | 731 | 0.276 | 0.24–0.31 | +0.07 | 25 | 0.320 | +0.04 | -0.044 |
| prime_nette_jour | 830 | 564 | 0.261 | 0.23–0.30 | +0.03 | 229 | 0.323 | +0.18 | -0.063 |
| regime_marche | 830 | 411 | 0.226 | 0.19–0.27 | -0.14 | 419 | 0.317 | +0.24 | -0.091 |
| au_dessus_flip | 132 | 72 | 0.181 | 0.11–0.28 | -0.25 | 60 | 0.300 | +0.03 | -0.119 |
| regime_secteur | 94 | 50 | 0.160 | 0.08–0.28 | -0.50 | 41 | 0.317 | +0.70 | -0.157 |
| analystes | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| congres | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| dark_pool | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| etf | 830 | 0 | nan | 0.00–1.00 | +nan | 252 | 0.274 | +0.01 | +nan |
| flux | 136 | 136 | 0.243 | 0.18–0.32 | -0.05 | 0 | nan | +nan | +nan |
| inities | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| macro_lendemain | 830 | 0 | nan | 0.00–1.00 | +nan | 231 | 0.303 | +0.29 | +nan |
| mega_cap | 830 | 0 | nan | 0.00–1.00 | +nan | 129 | 0.279 | +0.15 | +nan |
| open_interest | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| resultats_7j | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| saisonnalite | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| short_volume | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |

## Score du desk actuel (dans le sens du signal)

| Score | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|
| 0–45 | 162 | 0.340 | 0.27–0.41 | +0.30 |
| 45–55 | 169 | 0.231 | 0.17–0.30 | -0.16 |
| 55–65 | 180 | 0.294 | 0.23–0.36 | +0.15 |
| 65–75 | 180 | 0.289 | 0.23–0.36 | +0.20 |
| 75–101 | 139 | 0.194 | 0.14–0.27 | -0.31 |

## Score appris (dates < 2026-08-28) puis testé (dates ≥ 2026-08-28)

Facteurs retenus sur la première moitié : gamma_negatif, liquidite_os, murs_gamma, screener.

| Échantillon | Votes nets | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|---|
| apprentissage | < 0 | 11 | 0.091 | 0.02–0.38 | -0.27 |
| apprentissage | 0 | 35 | 0.200 | 0.10–0.36 | -0.36 |
| apprentissage | 1 | 18 | 0.389 | 0.20–0.61 | +0.38 |
| apprentissage | ≥2 | 330 | 0.294 | 0.25–0.34 | +0.38 |
| test | < 0 | 7 | 0.000 | 0.00–0.35 | -1.45 |
| test | 0 | 33 | 0.182 | 0.09–0.34 | -0.42 |
| test | 1 | 24 | 0.208 | 0.09–0.41 | -0.44 |
| test | ≥2 | 372 | 0.277 | 0.23–0.32 | -0.11 |

## Filtre gamma : repéré sur le panel flux, testé sur le panel screener

Règle : murs gamma favorables (> 0) ET gamma des dealers négatif.

| Panel | Règle | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|---|
| flux (découverte) | vérifiée | 38 | 0.342 | 0.21–0.50 | +0.21 |
| flux (découverte) | murs seuls > 0 | 103 | 0.291 | 0.21–0.39 | +0.02 |
| flux (découverte) | non vérifiée | 94 | 0.191 | 0.12–0.28 | -0.26 |
| flux (découverte) | tous | 132 | 0.235 | 0.17–0.31 | -0.13 |
| screener (test) | vérifiée | 0 | nan | 0.00–1.00 | +nan |
| screener (test) | murs seuls > 0 | 0 | nan | 0.00–1.00 | +nan |
| screener (test) | non vérifiée | 0 | nan | 0.00–1.00 | +nan |
| screener (test) | tous | 0 | nan | 0.00–1.00 | +nan |

Lecture : un facteur utile a un « gain » nettement plus haut quand il confirme que quand il contredit, et un mouvement moyen positif quand il confirme. Avec moins de 300 signaux sur deux mois, un écart de moins de 10 points n'est pas distinguable du bruit.
