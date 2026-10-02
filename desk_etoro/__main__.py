"""Ligne de commande du desk eToro.

  python -m desk_etoro run [--date AAAA-MM-JJ] [--config f.json] [--snapshot DOSSIER] [--hors-ligne]
  python -m desk_etoro planifier [--avance 60]   # boucle : un run par semaine avant l'ouverture
  python -m desk_etoro prochaine-revue
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

from . import rapport
from .calendrier import NY, est_jour_de_revue, prochaine_revue
from .client import ClientEtoro
from .config import Config
from .desk import executer
from .reequilibrage import ecrire_etat, lire_etat
from .sources import Collecteur, Snapshot

log = logging.getLogger("desk_etoro")


def notifier(message: str) -> None:
    log.info(message)
    url = os.environ.get("NTFY_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST", headers={"Title": "Desk eToro"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as e:  # une notification ratée ne doit pas arrêter le desk
        log.error("notification impossible : %s", e)


def lancer(cfg: Config, jour: dt.date, snapshot: Path | None = None, hors_ligne: bool = False,
           enregistrer_etat: bool = True) -> Path:
    racine = cfg.dossier_donnees
    snap = Snapshot(snapshot or racine / "snapshots" / jour.isoformat())
    client = None if hors_ligne else ClientEtoro(cfg.connexion)
    chemin_etat = racine / "etat.json"
    etat = lire_etat(chemin_etat)
    if etat.get("date") == jour.isoformat():  # relance le même jour : on repart de l'état précédent
        precedent = racine / "etat_precedent.json"
        etat = lire_etat(precedent) if precedent.exists() else {"date": None, "lignes": {}}
    res = executer(cfg, Collecteur(snap, client, jour), jour, etat)

    sortie = racine / "runs" / jour.isoformat()
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / "plan.json").write_text(json.dumps(rapport.plan(res, cfg), ensure_ascii=False, indent=1), encoding="utf-8")
    (sortie / "rapport.md").write_text(rapport.markdown(res, cfg), encoding="utf-8")
    if enregistrer_etat:
        if chemin_etat.exists() and lire_etat(chemin_etat).get("date") != jour.isoformat():
            (racine / "etat_precedent.json").write_text(chemin_etat.read_text(encoding="utf-8"), encoding="utf-8")
        ecrire_etat(chemin_etat, jour.isoformat(), res.cible)
    actifs = [o for o in res.ordres if o.action != "CONSERVER"]
    notifier(f"Desk eToro {jour} : {len(res.cible.lignes)} lignes, exposition {res.cible.exposition_brute:.0%}, "
             f"{len(actifs)} ordres ({', '.join(f'{o.action} {o.symbol}' for o in actifs[:8])}). Rapport : {sortie}")
    return sortie


def planifier(cfg: Config, avance_min: int) -> None:
    """Un run par semaine, lancé `avance_min` minutes avant l'ouverture de la première séance."""
    avance = dt.timedelta(minutes=avance_min)
    while True:
        maintenant = dt.datetime.now(NY)
        jour = maintenant.date()
        fait = (cfg.dossier_donnees / "runs" / jour.isoformat() / "plan.json").exists()
        ouverture = dt.datetime.combine(jour, dt.time(9, 30), NY)
        # Jour de revue : on lance dès l'heure de collecte, et jusqu'à la clôture en cas de redémarrage
        if est_jour_de_revue(jour) and not fait and ouverture - avance <= maintenant < ouverture.replace(hour=16, minute=0):
            try:
                lancer(cfg, jour)
            except Exception as e:
                notifier(f"Desk eToro : échec du run du {jour} : {e!r}")
                log.exception("échec du run")
                time.sleep(900)
            continue
        revue = prochaine_revue(maintenant)
        depart = revue - avance
        log.info("prochaine revue %s, collecte à %s", revue.isoformat(), depart.isoformat())
        time.sleep(min(max(60.0, (depart - maintenant).total_seconds()), 6 * 3600))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    ap = argparse.ArgumentParser(prog="desk_etoro", description="Desk eToro : consensus des Popular Investors")
    ap.add_argument("--config", type=Path, default=None)
    sous = ap.add_subparsers(dest="commande", required=True)
    r = sous.add_parser("run", help="un run complet (collecte, analyse, rapport)")
    r.add_argument("--date", type=dt.date.fromisoformat, default=None)
    r.add_argument("--snapshot", type=Path, default=None, help="dossier d'instantané à lire / compléter")
    r.add_argument("--hors-ligne", action="store_true", help="n'appelle pas eToro : instantané seul")
    r.add_argument("--sans-etat", action="store_true", help="ne met pas à jour etat.json")
    p = sous.add_parser("planifier", help="boucle hebdomadaire")
    p.add_argument("--avance", type=int, default=60, help="minutes de collecte avant l'ouverture")
    sous.add_parser("prochaine-revue")
    a = ap.parse_args(argv)
    cfg = Config.charger(a.config)
    if a.commande == "run":
        jour = a.date or dt.datetime.now(NY).date()
        sortie = lancer(cfg, jour, a.snapshot, a.hors_ligne, not a.sans_etat)
        print(sortie / "rapport.md")
    elif a.commande == "planifier":
        planifier(cfg, a.avance)
    else:
        print(prochaine_revue(dt.datetime.now(NY)).isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
