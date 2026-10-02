"""Collecte des données eToro avec mise en cache dans un instantané (snapshot) daté.

Chaque donnée lue est écrite dans <dossier>/<nom>.json : relancer l'analyse ne refait aucun appel,
et un instantané peut aussi être rempli par une autre voie (connecteur eToro d'une session Claude).
Sans client (mode hors ligne), une donnée absente de l'instantané renvoie None.

Unités (relevées sur l'API, cf. README) : classements v2 → gains en fractions mais drawdowns,
winRatio et *Pct en pourcentage ; gains v2 → fractions ; actifs v2 → fractions ;
portefeuille live v1 → investmentPct et netProfit en pourcentage.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

from .client import ClientEtoro, ErreurApi

log = logging.getLogger("desk_etoro")


def _nom_fichier(texte: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", texte)


class Snapshot:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)

    def chemin(self, nom: str) -> Path:
        return self.dossier / f"{nom}.json"

    def lire(self, nom: str):
        p = self.chemin(nom)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def ecrire(self, nom: str, donnees) -> None:
        p = self.chemin(nom)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)


class Collecteur:
    def __init__(self, snapshot: Snapshot, client: ClientEtoro | None, aujourd_hui: dt.date):
        self.snap, self.client, self.jour = snapshot, client, aujourd_hui

    def _obtenir(self, nom: str, appel):
        deja = self.snap.lire(nom)
        if deja is not None:
            return None if isinstance(deja, dict) and "_erreur" in deja else deja
        if self.client is None:
            return None
        try:
            donnees = appel()
        except ErreurApi as e:
            # profil privé, désinscrit ou inconnu, ou réponse trop lourde pour le relais MCP : on n'insiste pas
            if e.statut in (400, 403, 404, 413):
                log.info("%s indisponible (%s)", nom, e.statut)
                self.snap.ecrire(nom, {"_erreur": e.statut})
                return None
            raise
        self.snap.ecrire(nom, donnees)
        return donnees

    # -- Univers ------------------------------------------------------------------------------
    def classement(self, periode: str, popular_investor: bool = True) -> list[dict]:
        """Tous les investisseurs classés pour la période (pages de 100, doublons retirés)."""
        def appel():
            lignes, page = [], 1
            while True:
                q = {"period": periode, "page": page, "pageSize": 100, "sort": "-copiers"}
                if popular_investor:
                    q["popularInvestor"] = "true"
                rep = self.client.get("/api/v2/portfolios/rankings", q)
                lignes += rep.get("results") or []
                if not (rep.get("pagination") or {}).get("hasNext"):
                    return lignes
                page += 1
        brut = self._obtenir(f"classements/{periode}", appel) or []
        vus, uniques = set(), []
        for l in brut:
            cle = (l.get("username") or "").lower()
            if cle and cle not in vus:
                vus.add(cle)
                uniques.append(l)
        return uniques

    # -- Portefeuilles ------------------------------------------------------------------------
    def portefeuille_live(self, username: str) -> dict | None:
        return self._obtenir(f"live/{_nom_fichier(username)}", lambda: self.client.get(
            f"/api/v1/user-info/people/{username}/portfolio/live", pool="live"))

    def actifs(self, username: str, jours: int = 37) -> dict | None:
        """Répartition quotidienne sur `jours` jours (GET /api/v2/portfolios/{u}/assets/history), copies exclues."""
        def appel():
            debut = (self.jour - dt.timedelta(days=jours)).isoformat()
            return self.client.get(f"/api/v2/portfolios/{username}/assets/history",
                                   {"minDate": debut, "maxDate": self.jour.isoformat()})
        return self._obtenir(f"actifs/{_nom_fichier(username)}", appel)

    def gains(self, username: str, granularite: str = "monthly", nb: int = 36) -> list[tuple[str, float]]:
        """Rendements périodiques (fractions) les plus récents, du plus ancien au plus récent."""
        rep = self._obtenir(f"gains/{_nom_fichier(username)}", lambda: self.client.get(
            f"/api/v2/portfolios/{username}/gain/{granularite}", {"count": nb}))
        if not rep:
            return []
        points = [(g["date"], float(g["gain"])) for g in rep.get("gains") or [] if g.get("gain") is not None]
        return sorted(points)

    # -- Instruments --------------------------------------------------------------------------
    def instruments(self, ids: list[int]) -> dict[int, dict]:
        """Ticker, nom et classe d'actif (GET /api/v2/market-data/instruments)."""
        connus = {int(k): v for k, v in (self.snap.lire("instruments") or {}).items()}
        manquants = sorted({int(i) for i in ids} - set(connus))
        if manquants and self.client is not None:
            for i in range(0, len(manquants), 200):
                lot = manquants[i:i + 200]
                jeton = None
                while True:
                    q = {"instrumentsIds": ",".join(map(str, lot)), "pageSize": len(lot)}
                    if jeton:
                        q["pageToken"] = jeton
                    try:
                        rep = self.client.get("/api/v2/market-data/instruments", q, pool="marche")
                    except ErreurApi as e:
                        if e.statut == 404:
                            break
                        raise
                    for r in rep.get("results") or []:
                        connus[int(r["instrumentId"])] = {
                            "symbol": r.get("symbol") or "", "nom": (r.get("displayName") or "").strip(),
                            "type": r.get("type") or "", "exchangeId": r.get("exchangeId")}
                    pag = rep.get("pagination") or {}
                    if not pag.get("hasNext"):  # le jeton n'est jamais nul : on suit hasNext
                        break
                    jeton = pag.get("nextPageToken")
            self.snap.ecrire("instruments", {str(k): v for k, v in connus.items()})
        return {i: connus[i] for i in ids if int(i) in connus}

    def eligibilite(self, ids: list[int]) -> dict[int, dict]:
        """Conditions de trading du compte connecté (leviers permis, bornes du stop) par instrument."""
        connus = {int(k): v for k, v in (self.snap.lire("eligibilite") or {}).items()}
        manquants = sorted({int(i) for i in ids} - set(connus))
        if manquants and self.client is not None:
            for i in range(0, len(manquants), 100):
                lot = manquants[i:i + 100]
                rep = self.client.post_lecture("/api/v2/trading/info/eligibility",
                                               {"instrumentIds": lot, "currency": "USD"}, pool="eligibilite")
                for e in rep.get("eligibilities") or []:
                    connus[int(e["instrumentId"])] = e
            self.snap.ecrire("eligibilite", {str(k): v for k, v in connus.items()})
        return {i: connus[i] for i in ids if int(i) in connus}

    def cours(self, instrument_id: int, nb: int = 300) -> list[tuple[str, float]]:
        """Clôtures quotidiennes (date, cours), du plus ancien au plus récent, séance en cours exclue."""
        def appel():
            rep = self.client.get(
                f"/api/v1/market-data/instruments/{instrument_id}/history/candles/asc/OneDay/{nb}", pool="marche")
            bougies = []
            for groupe in rep.get("candles") or []:
                for b in groupe.get("candles") or []:
                    if b.get("close") is not None:
                        bougies.append([b["fromDate"][:10], float(b["close"])])
            return {"instrumentId": instrument_id, "closes": bougies}
        rep = self._obtenir(f"cours/{instrument_id}", appel)
        if not rep:
            return []
        clotures = sorted((d, float(c)) for d, c in rep.get("closes") or [])
        return [(d, c) for d, c in clotures if d < self.jour.isoformat()]
