# Robot d'exécution IBKR des desks + Desk Flow (Unusual Whales)

Exécute **automatiquement** dans IBKR les tickets produits par les desks
(Desk Swing Options, Desk Stock Scanner) : entrée conditionnelle, TP, SL,
stop du sous-jacent et sortie temps, sans validation manuelle.

> ⚠️ Compte réel. Le robot démarre en **simulation** (`DRY_RUN=true`) : il annonce
> ce qu'il ferait sans rien envoyer. Ne passez à `DRY_RUN=false` qu'après avoir
> vérifié plusieurs jours de simulations.

## Fonctionnement

```
Desk (run Claude du matin) ──► tickets/<date>-<desk>.json (ce dépôt, git)
                                         │  git pull toutes les 5 min (cron du VPS)
                                         ▼
VPS : robot (Python, ib_async) ◄──► IB Gateway + IBC (Docker) ◄──► IBKR
```

À chaque minute, le robot :
1. lit les tickets du jour et refuse ceux qui sont invalides ;
2. applique les **garde-fous** : limite ≤ plafond, risque ≤ 2 % de la NAV (+10 %),
   prime ≤ 3 %, risque cumulé ≤ 10 %, 3 nouveaux ordres par jour au plus,
   5 contrats au plus, un seul trade par action. Un refus bloque le ticket ;
3. envoie l'entrée : ordre limite DAY, avec la **condition sur le cours de l'action**,
   et le **TP** attaché (ordre limite GTC chez IBKR) ;
4. surveille les positions ouvertes pendant la séance : **SL** sur la valeur du combo,
   **clôture de l'action au-delà du stop** (à partir de 15 h 55), **sortie temps**.
   Il sort alors à cours limité exécutable (bid à la vente, ask au rachat), recoté toutes les 3 minutes s'il n'est pas exécuté ;
5. notifie chaque étape (journal + téléphone via ntfy si `NTFY_URL` est défini).

Le SL est surveillé par le robot et non posé chez IBKR, car les ordres stop sur combos
d'options y sont peu fiables. **Si le robot est arrêté, le SL n'est plus surveillé** (le TP, lui, reste chez IBKR).

## Desk Flow : opportunités horaires Unusual Whales → ordres IBKR

Le **scanner** (`scanner/`) interroge toutes les heures l'API Unusual Whales, note les titres par
confluence, construit le spread d'options le plus rentable (espérance par dollar risqué), le dimensionne
sur la NAV IBKR et dépose le ticket dans `tickets/<date>-flow.json` : le robot ci-dessus l'exécute.

```
UW (REST : tide, secteurs, GEX, flow alerts, screeners, dark pool, OI, initiés, Congrès, analystes,
    short interest, max pain, IV, saisonnalité, chaînes)  ──► scanner (10h05 … 15h05 NY)
    ──► tickets/<date>-flow.json + reports/<date>-<heure>-flow.md ──► robot ──► IBKR
```

À chaque scan :
1. **Régime** : market tide (pente 1 h + niveau), tide des 11 secteurs, gamma SPY, calendrier macro
   (événement dans les 2 h → risk-off : rapport seulement) ;
2. **Candidats** : flow alerts (90 min), hottest chains haussiers/baissiers, dark pool ≥ 5 M$, OI changes,
   initiés, Congrès ; univers actions/ADR/ETF ≥ 2 Md$, prix 8–1 500 $ ;
3. **Enrichissement** des 15 titres les plus chauds (15 flux par titre : prix/ATR/SMA, murs gamma,
   exposition gamma, net premium, OI du titre, dark pool du titre, short interest, max pain, IV rank,
   analystes, initiés, saisonnalité, chaîne cotée) ;
4. **Score** 0–100 (poids dans `scanner/scoring.py`), direction, seuil 55 ;
5. **Structure** : vertical débit (IV rank < 55 %) ou crédit (≥ 55 %), échéance 21–50 j hors résultats,
   limite/plafond/TP/SL, condition d'entrée sur l'action, stop action, sortie temps à 10 jours (l'effet du flux
   d'options sur l'action se mesure sur quelques jours à une semaine) ;
6. **Taille** dans les garde-fous du robot, probabilité de gain calibrée sur l'historique
   (`python -m scanner.calibrate`, résultat dans `scanner/calibration.json` et `reports/calibration.md`),
   classement par **EV / $ risqué**, au plus 3 tickets par scan
   et 3 ordres par jour ; délai de carence de 3 jours par titre ; jamais un titre déjà en position.

Configuration : `UW_TOKEN` (obligatoire) et les variables `MIN_SCORE`, `MAX_TICKETS_PER_RUN`, `LOOKBACK_MINUTES`,
`MIN_DTE`/`MAX_DTE`, `IV_RANK_CREDIT`, `EXCLUDE_SYMBOLS`… de `.env.example`. Un scan manuel :
`docker compose run --rm scanner python -m scanner.main --once`. Rapport du dernier scan : `reports/dernier-flow.md`.
Sans IB Gateway joignable, la NAV vient de `NAV_USD`.

**Depuis Claude** : le skill `/desk-flow` (`.claude/skills/desk-flow/SKILL.md`) exécute le même run avec les
connecteurs Unusual Whales et IBKR, crée les **instructions d'ordre** dans IBKR (à soumettre dans l'app) et
dépose tickets (`tickets/<date>-flow-ia.json`, desk `flow-ia`) et rapports (`reports/ia/`) dans le dépôt.
Une Routine Claude peut le lancer toutes les heures de séance (elle doit être créée depuis l'interface Routines
de claude.ai avec les connecteurs Unusual Whales et IBKR attachés). Premier run réel : `reports/ia/2026-10-02-0925-flow-ia.md`.

## Installation sur un VPS

1. Louer un VPS Linux (2 Go de RAM suffisent ; Hetzner, OVH, DigitalOcean…), installer Docker
   et git, n'ouvrir que SSH (`ufw allow OpenSSH && ufw enable`).
2. Cloner ce dépôt avec une **clé de déploiement en lecture seule** (GitHub → Settings → Deploy keys).
3. `cp .env.example .env && chmod 600 .env`, puis remplir les identifiants IBKR, `IB_ACCOUNT_ID`, `NTFY_URL`.
   Conseil : créer dans IBKR un **utilisateur secondaire** dédié au robot (Paramètres → Utilisateurs),
   avec ses propres identifiants et les seules permissions de trading nécessaires.
4. `docker compose up -d --build`, puis **valider la notification IB Key** sur le téléphone.
5. Récupérer les tickets toutes les 5 minutes : `crontab -e` puis
   `*/5 * * * * cd ~/Trade && git pull --ff-only -q`.
6. Suivre : `docker compose logs -f robot`.

**2FA** : IB Gateway redémarre chaque nuit sans nouvelle 2FA ; IBKR exige une nouvelle
validation IB Key environ **une fois par semaine** (en général le dimanche). Sans elle, le robot reste déconnecté
et vous alerte.

## Commandes utiles

| Action | Commande |
|---|---|
| **Arrêt d'urgence** (plus aucune nouvelle entrée, les sorties continuent) | `touch data/STOP` |
| Reprendre | `rm data/STOP` |
| Tout arrêter | `docker compose down` (le TP reste chez IBKR, le SL n'est plus surveillé) |
| Passer en réel | `DRY_RUN=false` dans `.env`, puis `docker compose up -d` |
| Voir l'état | `sqlite3 data/etat.sqlite "select id, statut, motif from suivis"` |

## Brancher les desks

Chaque run de desk doit déposer ses tickets dans `tickets/<AAAA-MM-JJ>-<desk>.json` sur la branche
clonée par le VPS (format : `tickets/README.md`). Les instructions IBKR que créent déjà les desks
ne sont pas des ordres : elles ne font pas double emploi, mais **ne les transmettez plus à la main**
une fois le robot en réel, sinon le trade serait pris deux fois.

## Développement

```
pip install -r requirements.txt pytest
python -m pytest -q tests
```

Limites connues : une entrée partiellement exécutée puis annulée est signalée « À VÉRIFIER » et laissée à gérer à la main ;
le robot ne gère que les positions qu'il a lui-même ouvertes ; sans abonnement IBKR aux données de marché via l'API, le SL ne peut pas être surveillé (le robot l'alerte).
