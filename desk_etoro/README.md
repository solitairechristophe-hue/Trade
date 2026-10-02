# Desk eToro : consensus des Popular Investors

Le desk explore **tous les portefeuilles de Popular Investors actifs** d'eToro, les investisseurs
du programme « pro » d'eToro, qui sont vérifiés, rémunérés et classés par paliers (Rising Star, Champion,
Elite, Elite Pro, Certified). Il note la qualité de chaque portefeuille, croise leurs compositions et
note chaque ticker selon sa présence pondérée par la qualité des portefeuilles qui le détiennent.
Il en tire un **portefeuille revu chaque semaine à l'ouverture**, où chaque ligne reçoit un poids et,
pour les valeurs à haut score qui supportent le levier, un **facteur multiplicateur**.

Le desk **propose** les ordres sans jamais les transmettre. L'exécution se fait à la main, ou par une
session Claude avec `prepare-trade` / `place-trade`, chaque ordre étant validé.

## Chaîne de traitement

```
Classements eToro (588 PI actifs) ─► filtres de risque ─► pré-qualité
        │                                                    │
        ▼                                                    ▼
périodes 3 mois / 6 mois / 2 ans          pour chaque portefeuille retenu :
                                            gains mensuels 36 mois  → critères calculés
                                            composition live         → poids par ticker
        └───────────────► note de qualité Q (5 familles, rangs centiles)
                                     │  vote = Q² (le quart le moins bien noté ne vote pas)
                                     ▼
                      croisement des tickers → score 0–100
                                     ▼
          portefeuille cible : sélection, poids, levier, stops ─► ordres de la revue
```

### 1. Univers

Toutes les lignes de `GET /api/v2/portfolios/rankings?popularInvestor=true` (pages de 100), sur la période
de référence (`OneYearAgo`) et sur les périodes complémentaires (`ThreeMonthsAgo`, `SixMonthsAgo`,
`LastTwoYears`). Un portefeuille est écarté s'il n'a pas de score de risque, si son score de risque dépasse 6
ou sa pointe mensuelle 7, s'il a moins d'un an d'ancienneté, s'il est actif moins d'une semaine sur deux,
investi à moins de 20 %, ou si plus de la moitié de ses trades se font à fort levier. Tous ces seuils sont
réglables (`config.Univers`). `paliers_admis` permet de se limiter, par exemple, à
`["pi-elite-pro", "pi-certified"]`.

### 2. Qualité d'un portefeuille

Pour chaque critère, on prend le rang centile du portefeuille dans l'univers. Les rangs sont moyennés par
famille, puis les familles sont pondérées.

| Famille (poids) | Critères fournis par eToro | Critères calculés |
|---|---|---|
| Performance (25 %) | gain 12 mois, 6 mois, 3 mois, 2 ans, rendement annualisé | CAGR 36 mois |
| Ajusté du risque (25 %) | gain / pire recul | Sharpe, Sortino, Calmar |
| Maîtrise du risque (20 %) | score de risque actuel, pics quotidien et mensuel, pire recul, pires baisses jour et semaine, part de trades à fort levier | volatilité, drawdown 36 mois, Ulcer index, diversification effective (1/HHI) |
| Régularité (15 %) | mois et semaines profitables, trades gagnants, semaines actives | mois positifs, R² de la courbe, pire mois, positions ouvertes gagnantes |
| Confiance (15 %) | copieurs, évolution des copieurs, encours (AUM), ancienneté, palier PI | — |

Les critères calculés viennent des gains mensuels (`GET /api/v2/portfolios/{u}/gain/monthly?count=36`).
Le vote d'un portefeuille vaut Q², ce qui donne plus de poids aux meilleurs. Le quart le moins bien noté ne vote pas.

### 3. Composition et croisement des tickers

La composition vient de `GET /api/v1/user-info/people/{u}/portfolio/live`. Chaque position est pondérée par
sa valeur actuelle, investissement × (1 + P&L latent). On garde aussi le sens (long ou court), le levier et la
date d'ouverture. Avec `source_composition = "actifs"`, la composition est lue dans
`/api/v2/portfolios/{u}/assets/history` : c'est plus léger, mais sans le sens ni le levier. La fraîcheur est
alors estimée par la hausse du montant investi sur 30 jours. Pour un ticker *i* :

- **consensus** : Σ vote·poids / Σ vote, soit le poids de *i* dans la copie pondérée de tous les portefeuilles (35 %) ;
- **largeur** : part, pondérée par le vote, des portefeuilles qui détiennent *i* (30 %) ;
- **conviction** : poids moyen de *i* chez ses détenteurs (15 %) ;
- **qualité des détenteurs** : moyenne de Q (12 %) ;
- **fraîcheur** : part du poids ouverte ou renforcée depuis moins de 30 jours (8 %).

Le score vaut 100 × la somme pondérée des rangs centiles. Il n'est calculé que pour les tickers détenus par
au moins 3 portefeuilles votants.

### 4. Portefeuille cible et facteur multiplicateur

- **Sélection** : les 20 meilleurs scores ≥ 60, hors devises, en consensus acheteur, ouvrables sur le
  compte. Une ligne déjà détenue reste tant que son rang est ≤ 30 et son score ≥ 50 (hystérésis), pour
  éviter de tourner pour rien.
- **Poids** : (score/100)² / volatilité^0,5, entre 2 % et 10 % par ligne, crypto ≤ 15 % au total,
  2 % de liquidités.
- **Levier** : seulement pour une valeur à **haut score**, ≥ 80, et **adaptée au levier**. Il faut que
  toutes ces conditions soient remplies :
  - action, ETF ou indice ;
  - volatilité annuelle ≤ 35 % (calculée sur les bougies quotidiennes eToro) ;
  - cours au-dessus de ses moyennes 50 et 200 jours ;
  - cours à moins de 25 % de son plus haut sur 52 semaines ;
  - levier proposé par eToro sur ce compte (`POST /api/v2/trading/info/eligibility`).

  Le multiplicateur est le plus grand levier permis, x2 au plus par défaut, tel que levier × volatilité
  ≤ 50 %. L'exposition brute du portefeuille (Σ poids × levier) est plafonnée à 150 %. Au-delà, on retire
  d'abord le levier des lignes les moins bien notées.
- **Stop** : une ligne à levier reçoit un stop (obligatoire chez eToro). Il est placé à 2,5 × la
  volatilité hebdomadaire, entre 8 % et 30 %, dans les bornes eToro exprimées en % de la marge.

### 5. Revue hebdomadaire

Chaque semaine, à la première séance NYSE (lundi, ou mardi après un férié), à l'ouverture (9 h 30,
New York), la nouvelle cible est comparée à celle de la semaine passée (`etat.json`). Chaque ligne reçoit
une action : VENTE, CHANGER LEVIER (fermer puis rouvrir, car chez eToro le levier est attaché à la
position), ALLÉGER, ACHAT, RENFORCER ou CONSERVER. Un écart de poids inférieur à 1 point est ignoré.

## Utilisation

```
export ETORO_USER_KEY=…            # clé utilisateur eToro (secrète)
export ETORO_API_KEY=…             # clé de l'application (mode rest)
# sans clé d'application : ETORO_MODE=mcp passe par le serveur MCP eToro avec la seule clé utilisateur

python -m desk_etoro run                    # run complet maintenant
python -m desk_etoro run --hors-ligne --snapshot data/desk_etoro/snapshots/2026-10-02   # rejouer un instantané
python -m desk_etoro planifier              # boucle : collecte 60 min avant chaque ouverture de revue
python -m desk_etoro prochaine-revue
python -m desk_etoro --config mon_desk.json run   # surcharge des paramètres, ex. {"allocation": {"levier_max": 3}}
```

Chaque run produit :

- `data/desk_etoro/runs/<date>/rapport.md` : portefeuille cible, ordres, top tickers, top portefeuilles, méthode ;
- `data/desk_etoro/runs/<date>/plan.json` : la même chose, lisible par une machine, avec tous les critères de chaque portefeuille ;
- `data/desk_etoro/snapshots/<date>/` : les données brutes eToro ; relancer le run ne refait aucun appel ;
- `data/desk_etoro/etat.json` : la cible publiée, qui sert de référence pour la revue suivante.

Avec `NTFY_URL`, un résumé est poussé sur le téléphone.

Pour le déploiement sur le VPS, à côté du robot IBKR : ajouter les variables `ETORO_*` au `.env`, puis lancer
`docker compose --profile etoro up -d --build`. Le service `desk-etoro` tourne en boucle et lance la collecte
chaque semaine avant l'ouverture. Une collecte complète prend environ 15 minutes : environ 1 100 appels sous
les quotas de 60 requêtes par minute.

## Limites

- La composition d'un portefeuille est celle du moment : un Popular Investor peut l'avoir changée depuis.
  La fraîcheur atténue ce décalage sans le supprimer.
- Le consensus favorise les grandes capitalisations très détenues. Le score de largeur limite ce biais
  sans l'éliminer.
- `etat.json` suppose que la cible de la semaine passée a été appliquée. Si le compte réel s'en écarte,
  les ordres proposés sont à ajuster.
- Le levier amplifie les pertes. Les conditions ci-dessus ne garantissent rien en cas de gap ou de
  décrochage de marché. Le desk est une aide à la décision, pas un conseil en investissement.
