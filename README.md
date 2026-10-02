# Robot d'exécution IBKR des desks

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
pip install ib_async pytest
python -m pytest -q tests
```

Limites connues : une entrée partiellement exécutée puis annulée est signalée « À VÉRIFIER » et laissée à gérer à la main ;
le robot ne gère que les positions qu'il a lui-même ouvertes ; sans abonnement IBKR aux données de marché via l'API, le SL ne peut pas être surveillé (le robot l'alerte).
