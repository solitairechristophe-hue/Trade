# Tickets à exécuter

Le robot lit ici chaque fichier `*.json` (un par run de desk, ex. `2026-10-02-swing.json`)
et n'exécute que les tickets du jour (`run_date` ≤ aujourd'hui ≤ `valid_until`).
Un ticket n'est envoyé qu'une fois : son `id` doit être unique.

Format (voir `exemple.json.txt`) :

| Champ | Sens |
|---|---|
| `id` | identifiant unique, ex. `swing-2026-10-02-SMCI` |
| `symbol`, `direction` | action sous-jacente ; `up` haussier, `down` baissier |
| `side` | `BUY` = débit, `SELL` = crédit (jambes toujours dans le sens débit, prix positifs) |
| `quantity` | nombre de combos |
| `limit_price`, `price_cap` | limite d'entrée et plafond (le robot refuse si limite > plafond) |
| `take_profit`, `stop_loss` | valeurs du combo pour le TP et le SL |
| `max_loss`, `premium` | perte maximale et prime du trade, en dollars |
| `legs` | `expiry` (AAAAMMJJ), `strike`, `right` (C/P), `action` (BUY/SELL), `ratio` |
| `condition` | facultatif : `{"op": ">=", "price": 42.10}` sur le cours de l'action |
| `underlying_stop` | facultatif : clôture de l'action au-delà = sortie |
| `time_exit` | facultatif : date de sortie temps |
| `valid_until` | facultatif : dernier jour d'envoi (par défaut `run_date`) |
