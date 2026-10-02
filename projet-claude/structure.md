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
si la prime dépasse le budget ; limite = mid + 15 % du spread, plafond = limite × 1,07, TP = limite + 55 % × (largeur − limite),
SL = 50 % de la limite ; prime = limite × 100 ; risque = (limite − SL) × 110.
Crédit : courte ~delta 0,25, longue 0,5–2 ATR plus loin, crédit ≥ 20 % de la largeur ; limite = mid − 15 % du spread,
plafond = limite, TP = 50 % du crédit, SL = 150 % du crédit ; jambes décrites dans le sens débit, side SELL.
Condition d'entrée ±0,15 ATR, stop action 1,5 ATR (ou au-delà du mur gamma), sortie temps = échéance − 7 j.
Quantité = min(2 % NAV / risque par combo, 3 % NAV / prime par combo (débit), 5). p = 0,38 + 0,24 × score/100.
EV = p × gain TP − (1 − p) × perte SL ; classement par EV / $ risqué, EV > 0 seulement.
