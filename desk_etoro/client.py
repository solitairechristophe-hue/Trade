"""Client minimal de l'API publique eToro (lecture seule).

Deux transports, mêmes identifiants (x-user-key + x-api-key, ou un jeton Bearer seul) :
  - rest : appel direct de l'API (ETORO_API_BASE, par défaut https://public-api.etoro.com) ;
  - mcp  : passage par le serveur MCP eToro (outil execute-read), utile si l'API directe est filtrée.
Le client respecte les quotas par groupe de routes et réessaie sur 429 / 5xx / délai dépassé.
Il n'expose que des lectures : aucune route qui passe un ordre n'est accessible d'ici.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque

from .config import Connexion

log = logging.getLogger("desk_etoro")

# Quotas (requêtes / 60 s) relevés dans la spécification : on garde 10 % de marge.
QUOTAS = {
    "defaut": 60,  # pool partagé : classements, gains, actifs, copieurs…
    "live": 60,  # /user-info/people/{u}/portfolio/live (dédié)
    "marche": 120,  # /market-data/* (pool partagé de 11 routes)
    "eligibilite": 20,  # /trading/info/eligibility (dédié)
}
FENETRE = 60.0


class ErreurApi(RuntimeError):
    def __init__(self, statut: int, message: str):
        super().__init__(f"HTTP {statut} : {message[:300]}")
        self.statut = statut


class Limiteur:
    def __init__(self, quotas: dict[str, int] = QUOTAS, marge: float = 0.9, horloge=time.monotonic,
                 sommeil=time.sleep):
        self.quotas = {k: max(1, int(v * marge)) for k, v in quotas.items()}
        self.appels: dict[str, deque] = {k: deque() for k in quotas}
        self.horloge, self.sommeil = horloge, sommeil

    def attendre(self, pool: str) -> None:
        file, quota = self.appels[pool], self.quotas[pool]
        while True:
            maintenant = self.horloge()
            while file and maintenant - file[0] >= FENETRE:
                file.popleft()
            if len(file) < quota:
                file.append(maintenant)
                return
            self.sommeil(FENETRE - (maintenant - file[0]) + 0.05)


class ClientEtoro:
    def __init__(self, cx: Connexion, limiteur: Limiteur | None = None, sommeil=time.sleep, essais: int = 5):
        if not (cx.bearer or cx.x_user_key):
            raise ValueError("identifiants eToro absents : définir ETORO_USER_KEY (+ ETORO_API_KEY) ou ETORO_BEARER")
        if cx.mode == "rest" and cx.x_user_key and not cx.x_api_key:
            raise ValueError("ETORO_API_KEY (clé de l'application) est requise avec ETORO_USER_KEY en mode rest")
        self.cx = cx
        self.limiteur = limiteur or Limiteur(sommeil=sommeil)
        self.sommeil = sommeil
        self.essais = essais

    # -- API publique du client -------------------------------------------------------------
    def get(self, chemin: str, query: dict | None = None, pool: str = "defaut"):
        return self._appel(chemin, query, None, pool)

    def post_lecture(self, chemin: str, corps: dict, pool: str = "defaut"):
        """POST à sémantique de lecture (ex. éligibilité) : rien n'est modifié côté eToro."""
        return self._appel(chemin, None, corps, pool)

    # -- Mécanique ---------------------------------------------------------------------------
    def _entetes(self, id_requete: str) -> dict:
        h = {"Accept": "application/json", "x-request-id": id_requete}
        if self.cx.bearer:
            h["Authorization"] = f"Bearer {self.cx.bearer}"
        else:
            h["x-user-key"] = self.cx.x_user_key
            if self.cx.x_api_key:
                h["x-api-key"] = self.cx.x_api_key
        return h

    def _appel(self, chemin: str, query: dict | None, corps: dict | None, pool: str):
        query = {k: str(v) for k, v in (query or {}).items() if v is not None}
        id_requete = str(uuid.uuid4())
        attente = 2.0
        for essai in range(1, self.essais + 1):
            self.limiteur.attendre(pool)
            try:
                if self.cx.mode == "mcp":
                    statut, texte, apres = self._mcp(chemin, query, corps, id_requete)
                else:
                    statut, texte, apres = self._rest(chemin, query, corps, id_requete)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                statut, texte, apres = 0, repr(e), None
            if 200 <= statut < 300:
                return json.loads(texte) if texte else None
            reessayable = statut in (0, 429) or statut >= 500
            if not reessayable or essai == self.essais:
                raise ErreurApi(statut, texte)
            pause = apres if apres else attente
            log.warning("eToro %s → %s, nouvel essai dans %.0f s", chemin, statut or "délai", pause)
            self.sommeil(pause)
            attente = min(attente * 2, 60)
        raise ErreurApi(0, "épuisé")  # pragma: no cover

    def _rest(self, chemin, query, corps, id_requete):
        url = self.cx.base_rest.rstrip("/") + chemin
        if query:
            url += "?" + urllib.parse.urlencode(query)
        entetes = self._entetes(id_requete)
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps).encode()
            entetes["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=donnees, headers=entetes, method="POST" if corps is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.cx.timeout) as rep:
                return rep.status, rep.read().decode("utf-8"), None
        except urllib.error.HTTPError as e:
            apres = e.headers.get("Retry-After") if e.headers else None
            return e.code, e.read().decode("utf-8", "replace"), float(apres) if apres and apres.isdigit() else None

    def _mcp(self, chemin, query, corps, id_requete):
        args: dict = {"path": chemin, "xRequestId": id_requete}
        if query:
            args["query"] = query
        if corps is not None:
            args["body"] = json.dumps(corps)
        rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "execute-read", "arguments": args}}
        entetes = self._entetes(id_requete)
        entetes.update({"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        req = urllib.request.Request(self.cx.url_mcp, data=json.dumps(rpc).encode(), headers=entetes, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.cx.timeout + 30) as rep:
                brut = rep.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), None
        return lire_reponse_mcp(brut)


def lire_reponse_mcp(brut: str) -> tuple[int, str, float | None]:
    """Extrait (statut, corps, attente) de la réponse JSON-RPC (éventuellement en flux SSE) de execute-read."""
    message = None
    for ligne in brut.splitlines():
        if ligne.startswith("data:"):
            message = json.loads(ligne[5:].strip())
    if message is None:
        message = json.loads(brut)
    if "error" in message:
        return 0, json.dumps(message["error"]), None
    resultat = json.loads(message["result"]["content"][0]["text"])
    if resultat.get("error") and not resultat.get("statusCode"):
        return 0, str(resultat["error"]), None
    if resultat.get("bodyTruncated"):
        return 413, "réponse tronquée par le serveur MCP (réduire la demande)", None
    return int(resultat.get("statusCode") or 0), resultat.get("body") or "", resultat.get("retryAfterSeconds")
