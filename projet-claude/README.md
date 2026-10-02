# Créer le projet Claude « Desk Flow »

1. claude.ai → Projets → Nouveau projet « Desk Flow ».
2. Instructions du projet : coller le contenu de `INSTRUCTIONS.md`.
3. Connaissances du projet : ajouter `SKILL.md`, `scoring.md`, `structure.md`, `tickets-README.md`, `calibration.md`.
4. Connecteurs : activer Unusual Whales et Interactive Brokers (IBKR) dans la conversation.
5. Chaque matin vers 11h30 (Paris) : « run ». Ajouter « et crée les instructions IBKR » ou « et crée les alertes »
   pour autoriser ces créations. Poser ensuite dans TWS les ordres conditionnels du bloc « Ordres à poser ».
6. Facultatif : une Routine à 11h15 (Paris) les jours ouvrés, créée depuis l'interface Routines dans ce projet
   avec les deux connecteurs, prompt « run », pour trouver le rapport prêt en arrivant.
