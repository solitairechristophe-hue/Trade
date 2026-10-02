# Backtest croisé du Desk Flow

136 signaux (136 flux, 0 screener seul), 17 séances (2026-08-06 → 2026-09-22), issue à 7 séances. Hasard au seuil 1 ATR : 0.250.

## Facteurs un par un (gain = mouvement ≥ 1 ATR dans le sens du signal)

| Facteur | Couverture | n confirme | gain | IC 95 % | mvt moyen (ATR) | n contredit | gain | mvt moyen | écart |
|---|---|---|---|---|---|---|---|---|---|
| analystes | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| au_dessus_flip | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| congres | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| dark_pool | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| etf | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| flux | 136 | 136 | 0.243 | 0.18–0.32 | -0.05 | 0 | nan | +nan | +nan |
| gamma_negatif | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| inities | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| iv_rank_bas | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| liquidite_os | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| macro_lendemain | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| mega_cap | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| momentum_5j | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| murs_gamma | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| open_interest | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| prime_nette_jour | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| regime_marche | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| regime_secteur | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| resultats_7j | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| rsi_extreme | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| saisonnalite | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| screener | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| short_volume | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| spy_gamma_positif | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |
| tendance | 0 | 0 | nan | 0.00–1.00 | +nan | 0 | nan | +nan | +nan |

## Score du desk actuel (dans le sens du signal)

| Score | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|
| 0–45 | 0 | nan | 0.00–1.00 | +nan |
| 45–55 | 0 | nan | 0.00–1.00 | +nan |
| 55–65 | 11 | 0.455 | 0.21–0.72 | +0.93 |
| 65–75 | 125 | 0.224 | 0.16–0.30 | -0.13 |
| 75–101 | 0 | nan | 0.00–1.00 | +nan |

## Score appris (dates < 2026-08-28) puis testé (dates ≥ 2026-08-28)

Facteurs retenus sur la première moitié : aucun.

| Échantillon | Votes nets | n | gain 1 ATR | IC 95 % | mvt moyen |
|---|---|---|---|---|---|
| apprentissage | < 0 | 0 | nan | 0.00–1.00 | +nan |
| apprentissage | 0 | 64 | 0.281 | 0.19–0.40 | +0.35 |
| apprentissage | 1 | 0 | nan | 0.00–1.00 | +nan |
| apprentissage | ≥2 | 0 | nan | 0.00–1.00 | +nan |
| test | < 0 | 0 | nan | 0.00–1.00 | +nan |
| test | 0 | 72 | 0.208 | 0.13–0.32 | -0.40 |
| test | 1 | 0 | nan | 0.00–1.00 | +nan |
| test | ≥2 | 0 | nan | 0.00–1.00 | +nan |

Lecture : un facteur utile a un « gain » nettement plus haut quand il confirme que quand il contredit, et un mouvement moyen positif quand il confirme. Avec moins de 300 signaux sur deux mois, un écart de moins de 10 points n'est pas distinguable du bruit.
