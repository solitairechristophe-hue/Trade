# Référence : structure et niveaux (extrait de scanner/structure.py)

```python
"""Choix de la structure d'options et des niveaux (fonctions pures sur la chaîne cotée).

Débit (défaut) : vertical acheté, jambe longue ~delta 0,50, jambe courte ~delta 0,25
(ou au mur gamma s'il est dans la fourchette), largeur 0,5 à 3 ATR, resserrée si la prime dépasse le budget. Crédit (IV rank élevé) : vertical vendu,
jambe courte ~delta 0,25, jambe longue plus loin ; SL à 150 % du crédit. Les jambes sont toujours décrites dans
le sens débit, comme l'exige le robot ; un crédit est la vente (side SELL) de ce combo.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
```

Débit : longue ~delta 0,50 (ou 0,40), courte ~delta 0,25 ou au mur gamma (0,8–2,5 ATR), largeur 0,5–3 ATR resserrée
si la prime dépasse le budget ; limite = mid, plafond = limite (aucune poursuite), TP = limite + 45 % × (largeur − limite),
SL = 50 % de la limite ; prime = limite × 100 ; risque = (limite − SL) × 110.
Crédit : courte ~delta 0,25, longue 0,5–2 ATR plus loin, crédit ≥ 20 % de la largeur ; limite = mid,
plafond = limite, TP = 50 % du crédit, SL = 150 % du crédit ; jambes décrites dans le sens débit, side SELL.
Condition d'entrée ±0,15 ATR, stop action 1,5 ATR (ou au-delà du mur gamma), sortie temps = run + 10 jours
calendaires (~7 séances), jamais après échéance − 7 j.
Quantité = min(2 % NAV / risque par combo, 3 % NAV / prime par combo (débit), 5).
p = p_min + (p_max − p_min) × score/100, p_min et p_max issus de la calibration (`calibration.md`), bornés à
[0,30 ; 0,70]. Mesure du 2 octobre 2026 : p_min 0,243 et p_max 0,259, donc **p = 0,30 quel que soit le score**.
EV = p × gain TP − (1 − p) × perte SL ; classement par EV / $ risqué, EV > 0 seulement.

## Mode matin, sans surveillance de séance
Le stop loss à 50 % de la prime n'est pas surveillé : la perte retenue est la perte maximale du spread
(prime entière pour un débit, (largeur − crédit) × 100 pour un crédit). Quantité = min(2 % NAV / perte maximale, 5).
EV = p × gain au TP − (1 − p) × perte maximale. Le TP reste posé chez IBKR en LIMIT GTC attaché à l'entrée.
Limite calculée sur le mid de clôture de la veille ; condition et stop action sur le cours de préouverture.

## Règles issues du backtest (2 octobre 2026, `backtest.md`)
- **Débit uniquement** : le spread à crédit n'est pas validé par le backtest.
- **Ratio IV 30 jours / volatilité prévue HAR ≤ 1,2**, sinon pas de trade. Trade baissier refusé si l'emprunt ≥ 10 %.
- Écart achat-vente cumulé des deux jambes ≤ 3 % de la largeur du spread, sinon pas de trade.
- Murs gamma contre le trade : rejet. Setup gamma obligatoire : murs favorables ET gamma des dealers négatif.
- Espérance du setup gamma avec option pas trop chère : +11,1 % de la prime (erreur type 6,4 %), soit EV = 0,111 × prime.
- Le score classe seulement ; il ne filtre pas.
- Taille d'essai : 1 combo par trade tant que 50 trades réels n'ont pas été journalisés.
