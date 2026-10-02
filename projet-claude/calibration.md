# Calibration de la probabilité de gain du Desk Flow — 2 octobre 2026

## En bref

Sur 136 signaux pris dans 17 séances (6 août – 22 septembre 2026), le flux d'options n'a **pas montré de pouvoir prédictif mesurable** sur 7 séances :

- **p_min = 0,243** (IC 95 % : 0,178 – 0,321), soit 33 gains sur 136 ;
- **p_max = 0,259** (IC 95 % : 0,132 – 0,447), soit 7 gains sur 27 dans le quintile au plus fort flux ;
- **taux de direction = 0,485**, c'est-à-dire du pile ou face.

Le tirage au hasard donne déjà 0,25 au seuil de 1 ATR sur ce même échantillon.

## Méthode

On a reproduit `scanner/calibrate.py`. Les données viennent toutes des outils MCP Unusual Whales.

1. **Séances de signal.** On a pris 17 séances, une sur deux environ, du 6 août au 22 septembre 2026 : 6, 10, 12, 14, 18, 20, 24, 26 et 28 août, puis 1er, 3, 8, 10, 14, 16, 18 et 22 septembre. Le 7 septembre (Labor Day) est exclu.
2. **Flux.** On a appelé `get_flow_alerts` sur la fenêtre 9 h 30 – 16 h 00 (heure de New York), avec ces filtres : prime ≥ 50 000 $, DTE de 5 à 90, actions, ADR et ETF, tri par prime, `limit` 100.
   - Pour chaque alerte, la prime est signée haussière si `(type == call) == (prime côté ask ≥ prime côté bid)`.
   - Son poids passe à 0,5 si l'échéance tombe 0 à 10 jours après des résultats encore à venir. C'est la règle de `poids_alerte`.
   - On fait ensuite la somme de la prime nette par titre. On garde les titres dont le symbole ne contient que des lettres et dont |net| ≥ 500 000 $, puis les 8 premiers par |net| à chaque séance.
3. **Cours.** On a pris les bougies journalières (OHLC) via `get_ticker_ohlc_latest_or_date`, du 8 juillet au 1er octobre 2026, soit 61 séances par titre. L'ATR14 est la moyenne des vrais écarts sur les 14 séances jusqu'au jour du signal inclus, comme dans `atr14()`.
4. **Issue.** On tient la position 7 séances. Un signal est **gagnant** si `(close[t+7] − close[t]) × direction ≥ 1,0 × ATR14`. On donne aussi deux mesures secondaires : le seuil à 0,5 × ATR14 et la direction seule (mouvement > 0).
5. **p_min et p_max.** p_min est le taux de gain sur tous les signaux. p_max est le taux sur le quintile supérieur par |prime nette|. Les intervalles sont de Wilson à 95 % (z = 1,96). Le calcul passe par `calibrer()` et `wilson()` de `scanner.calibrate`.

## Échantillon

| | |
|---|---|
| Séances de signal | 17 |
| Signaux évalués | 136 (aucun écarté faute de données) |
| Titres distincts | 70 (16 ETF, 54 actions et ADR) |
| Haussiers / baissiers | 66 / 70 |
| Quintile haut | 27 signaux (\|net\| ≥ 5,9 M$) |

Le détail par signal se trouve dans `reports/calibration-signaux.csv`.

## Résultats

| Critère de gain | Tous (n = 136) | IC 95 % | Quintile haut (n = 27) | IC 95 % | Hasard (½ · P(\|mvt\| ≥ seuil)) |
|---|---|---|---|---|---|
| **≥ 1 ATR (référence)** | **0,243** (33) | 0,178 – 0,321 | **0,259** (7) | 0,132 – 0,447 | 0,250 |
| ≥ 0,5 ATR | 0,353 (48) | 0,278 – 0,436 | 0,407 (11) | 0,245 – 0,593 | 0,364 |
| Direction (mvt > 0) | 0,485 (66) | 0,403 – 0,569 | 0,519 (14) | 0,340 – 0,693 | 0,500 |

En moyenne, le mouvement signé vaut −0,05 ATR et la médiane −0,05 ATR. On ne voit donc aucun déplacement systématique dans le sens du flux.

Les gains varient beaucoup d'une séance à l'autre : de 0 sur 8 (10 août, 18 septembre) à 5 sur 8 (24 août, 10 septembre). Cette dispersion vient surtout des mouvements d'ensemble du marché.

### Haussiers ou baissiers

| | n | ≥ 1 ATR | ≥ 0,5 ATR | Direction |
|---|---|---|---|---|
| Haussiers | 66 | **0,333** (0,232 – 0,453) | 0,379 | 0,470 |
| Baissiers | 70 | **0,157** (0,090 – 0,260) | 0,329 | 0,500 |

Au seuil de 1 ATR, les signaux haussiers font nettement mieux que les baissiers. Pourtant, leur taux de direction est le même, autour de 50 %. Les hausses ont simplement été plus amples que les baisses sur la période, une asymétrie propre à cette phase de marché. Il ne faut pas en conclure que seuls les signaux haussiers fonctionnent.

### ETF ou actions

| | n | ≥ 1 ATR | ≥ 0,5 ATR | Direction |
|---|---|---|---|---|
| ETF | 42 | 0,214 | 0,286 | 0,357 |
| Actions et ADR | 94 | 0,255 | 0,383 | 0,543 |

Sur les ETF, le flux est même légèrement à contre-sens. La plupart des gros puts sur SPY, QQQ et IWM sont probablement des couvertures et non des paris directionnels. Le flux sur actions individuelles fait à peine mieux que le hasard.

## Limites

- **Deux mois seulement et une seule phase de marché.** La période va d'août à septembre 2026. SPY est resté presque stable (768,6 → 764,0), avec une forte rotation sur les semi-conducteurs et la mémoire. Le résultat peut être très différent dans un marché en tendance ou en forte volatilité.
- **Petit échantillon.** Le quintile haut ne compte que 27 signaux. Son intervalle (0,13 – 0,45) est trop large pour mesurer un écart entre p_min et p_max.
- **On mesure le mouvement de l'action, pas le résultat du spread.** Le seuil de 1 ATR en 7 séances approche le déplacement nécessaire pour atteindre le take profit d'un vertical. Il ignore la prime payée, le theta, la vega, le choix des strikes, les sorties anticipées et le stop.
- **Biais de sélection.** On ne garde que le haut du tableau :
  - l'API ne renvoie que les 50 plus grosses alertes de la séance, même avec `limit` 100 ;
  - le filtre `max_dte` 90 ne semble pas appliqué côté API, car des échéances de décembre (plus de 90 jours) apparaissent. Le résultat est conservé tel quel, comme dans `calibrate.py`.

  Le flux sur indices et ETF mélange paris et couvertures, et le sens donné par le côté ask ou bid reste une approximation : spreads multi-jambes, ordres négociés en floor.
- **Événements ponctuels.** EYPT a perdu 67 % le 17 août et MRNA a gagné 177 % le 19 août. Le signal EYPT (baissier, 6 août, +9,5 ATR) compte comme un gain qu'aucun flux « informé » n'explique de façon fiable.
- **Signaux corrélés.** Plusieurs signaux d'une même séance ou d'un même titre (SPY, QQQ, NVDA, INTC…) sont corrélés. Les intervalles de Wilson, qui supposent des tirages indépendants, sont donc optimistes.

## Conclusion sur p_min et p_max

- **Aucune pente mesurable** : le quintile au plus fort flux (0,26) ne se distingue pas de l'ensemble (0,24), et les intervalles se recouvrent presque entièrement. Sur cette période, la taille du flux n'apporte aucune information sur la probabilité de gain.
- **Le niveau est bas.** Au seuil de 1 ATR, la probabilité observée (~0,24) se situe sous la valeur par défaut du desk (0,38 – 0,62). Elle est aussi sous le plancher de 0,30 appliqué par `charger_calibration()`.
- **Effet sur le scanner.** `scanner/calibration.json` est écrit tel que `calibrer()` le renvoie. Le scanner le lira et le bornera à **(0,30 ; 0,30)**, ce qui donne une probabilité plate de 0,30 quel que soit le score. C'est cohérent avec la mesure, car le flux ne différencie pas les signaux. Mais le dimensionnement deviendra plus prudent que l'actuel (0,38 – 0,62). Les spreads dont le ratio gain/perte est inférieur à environ 2,3 (seuil de rentabilité à p = 0,30) verront leur espérance passer sous zéro.
- **Recommandation.** Garder p_min = p_max ≈ 0,30 comme hypothèse prudente, ou ne pas activer ce fichier tant qu'on ne dispose pas d'un historique plus long. Il faudrait au moins 6 mois couvrant plusieurs régimes, avec plus de 500 signaux, pour estimer une pente. Il faudrait aussi :
  - mesurer le P&L réel des spreads plutôt que le mouvement de l'action ;
  - tester séparément le flux sur actions individuelles, hors ETF et couvertures d'indices ;
  - tester des filtres de qualité : `all_opening_trades`, sweep côté ask, volume supérieur à l'open interest.
