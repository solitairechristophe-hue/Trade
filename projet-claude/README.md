# Créer le projet Claude « Desk Flow »

1. claude.ai → Projets → Nouveau projet « Desk Flow ».
2. Instructions du projet : coller le contenu de `INSTRUCTIONS.md`.
3. Connaissances du projet : ajouter `SKILL.md`, `scoring.md`, `structure.md`, `tickets-README.md`.
4. Connecteurs : activer Unusual Whales et Interactive Brokers (IBKR) dans la conversation.
5. Lancer : « run » (ou « run, et crée les instructions IBKR » pour autoriser la création des brouillons d'ordre).
6. Routine horaire : créer depuis l'interface Routines, dans ce projet, avec les deux connecteurs,
   prompt « Fais le run du Desk Flow », cadence jours ouvrés 10h05–15h05 (New York).
