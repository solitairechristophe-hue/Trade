"""Boucle principale du robot.

À chaque cycle : lire les tickets du jour, mettre à jour les ordres suivis,
envoyer les nouvelles entrées qui passent les garde-fous, surveiller les sorties.
"""
from __future__ import annotations

import datetime as dt
import logging
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from .config import Config
from .exits import motif_sortie, prix_sortie, valeur_milieu
from .notify import Notifier
from .risk import refus
from .state import Etat, Suivi
from .tickets import tickets_du_jour

NY = ZoneInfo("America/New_York")
log = logging.getLogger("robot")


def seance_ouverte(m: dt.datetime) -> bool:
    return m.weekday() < 5 and dt.time(9, 30) <= m.time() < dt.time(16, 0)


def entrees_permises(m: dt.datetime) -> bool:
    # Ordres DAY : acceptés avant l'ouverture, pas dans le dernier quart d'heure
    return m.weekday() < 5 and m.time() < dt.time(15, 45)


def cycle(cfg: Config, broker, etat: Etat, notifier: Notifier, m: dt.datetime) -> None:
    jour = m.date()
    tickets, erreurs = tickets_du_jour(cfg.tickets_dir, jour)
    for e in erreurs:
        if etat.premiere_fois(e):
            notifier(f"Ticket ignoré : {e}", urgent=True)

    for s in etat.actifs():
        try:
            _suivre(cfg, broker, etat, notifier, s, m)
        except Exception as e:  # un trade en erreur ne bloque pas les autres
            if etat.premiere_fois(f"suivi {s.ticket.id} {jour} {e!r}"):
                notifier(f"Erreur de suivi {s.ticket.id} : {e!r}", urgent=True)

    if cfg.kill_switch_file.exists():
        log.info("Arrêt d'urgence actif (%s) : aucune nouvelle entrée", cfg.kill_switch_file)
        return
    if not entrees_permises(m):
        return
    nouveaux = [t for t in tickets if not etat.connu(t.id)]
    if not nouveaux:
        return

    nav = broker.nav()
    actifs = etat.actifs()
    risque_ouvert = sum(s.ticket.max_loss for s in actifs)
    occupes = {s.ticket.symbol for s in actifs}
    ordres = etat.entrees_du_jour(jour)
    for t in nouveaux:
        r = refus(t, nav, risque_ouvert, ordres, occupes, cfg)
        if r:
            etat.ajouter(t, "REFUSE", jour, "; ".join(r))
            notifier(f"REFUSÉ {t.id} ({t.symbol}) : {'; '.join(r)}", urgent=True)
            continue
        resume = (f"{t.side} {t.quantity} {t.symbol} limite {t.limit_price} TP {t.take_profit} SL {t.stop_loss}"
                  + (f", si action {t.condition.op} {t.condition.price}" if t.condition else ""))
        if cfg.dry_run:
            etat.ajouter(t, "SIMULE", jour)
            notifier(f"SIMULATION {t.id} : {resume} (DRY_RUN, rien n'est envoyé)")
        else:
            try:
                s = Suivi(t, "SOUMIS", jour, None, 0, 0, "")
                broker.placer_entree(t, s.ref_entree, s.ref_tp)
            except Exception as e:
                etat.ajouter(t, "REFUSE", jour, f"erreur IBKR : {e}")
                notifier(f"ÉCHEC {t.id} : {e}", urgent=True)
                continue
            etat.ajouter(t, "SOUMIS", jour)
            notifier(f"ORDRE ENVOYÉ {t.id} : {resume}")
        ordres += 1
        risque_ouvert += t.max_loss
        occupes.add(t.symbol)


def _suivre(cfg: Config, broker, etat: Etat, notifier: Notifier, s: Suivi, m: dt.datetime) -> None:
    t = s.ticket
    if s.statut == "SOUMIS":
        st = broker.statut(s.ref_entree)
        if st and st[0] == "Filled":
            s.statut, s.prix_entree = "OUVERT", st[1]
            notifier(f"EXÉCUTÉ {t.id} ({t.symbol}) à {st[1]:.2f}, TP {t.take_profit} posé chez IBKR")
        elif st and st[0] in ("Cancelled", "ApiCancelled", "Inactive") and st[1] > 0:
            # Exécution partielle puis annulation : quantité incertaine, on ne la gère pas seul
            broker.annuler(s.ref_tp)
            s.statut, s.motif = "A_VERIFIER", "exécution partielle"
            notifier(f"À VÉRIFIER {t.id} ({t.symbol}) : entrée partiellement exécutée, TP annulé, "
                     "position à gérer à la main", urgent=True)
        elif (st and st[0] in ("Cancelled", "ApiCancelled", "Inactive")) or (st is None and s.cree_le < m.date()):
            s.statut, s.motif = "EXPIRE", (st[0] if st else "ordre du jour non exécuté")
            notifier(f"EXPIRÉ {t.id} ({t.symbol}) : {s.motif}")
        else:
            return
        etat.maj(s)
        return

    if s.statut == "OUVERT":
        st_tp = broker.statut(s.ref_tp)
        if st_tp and st_tp[0] == "Filled":
            s.statut, s.motif = "CLOS", f"TP à {st_tp[1]:.2f}"
            etat.maj(s)
            notifier(f"CLOS {t.id} ({t.symbol}) : TP exécuté à {st_tp[1]:.2f}")
            return
        if not seance_ouverte(m):
            return
        bid, ask = broker.cotation(t)
        motif = motif_sortie(t, valeur_milieu(bid, ask), broker.cours(t.symbol), m)
        if bid is None or ask is None:
            if etat.premiere_fois(f"cotation {t.id} {m.date()}"):
                notifier(f"Pas de cotation pour {t.id} ({t.symbol}) : SL non surveillé "
                         "(abonnement aux données de marché API ?)", urgent=True)
            return
        if motif is None:
            return
        tp_actif = st_tp is not None and st_tp[0] not in ("Cancelled", "ApiCancelled", "Inactive")
        if motif == "TP" and tp_actif:
            return  # l'ordre TP posé chez IBKR s'en charge
        broker.annuler(s.ref_tp)
        s.sortie_n += 1
        s.statut, s.motif, s.boucles_sortie = "SORTIE_EN_COURS", motif, 0
        prix = prix_sortie(t, bid, ask)
        broker.placer_sortie(t, prix, s.ref_sortie)
        etat.maj(s)
        notifier(f"SORTIE {motif} {t.id} ({t.symbol}) : {t.exit_side} à {prix}", urgent=motif != "TP")
        return

    if s.statut == "SORTIE_EN_COURS":
        st = broker.statut(s.ref_sortie)
        if st and st[0] == "Filled":
            s.statut = "CLOS"
            s.motif = f"{s.motif} à {st[1]:.2f}"
            etat.maj(s)
            notifier(f"CLOS {t.id} ({t.symbol}) : {s.motif}")
            return
        if st and st[0] in ("Cancelled", "ApiCancelled", "Inactive"):
            s.statut = "OUVERT"  # ordre du jour expiré : la sortie sera réévaluée
            etat.maj(s)
            return
        if not seance_ouverte(m):
            return
        s.boucles_sortie += 1
        if s.boucles_sortie >= cfg.exit_reprice_loops:
            bid, ask = broker.cotation(t)
            if bid is not None and ask is not None:
                broker.annuler(s.ref_sortie)
                s.sortie_n += 1
                s.boucles_sortie = 0
                prix = prix_sortie(t, bid, ask)
                broker.placer_sortie(t, prix, s.ref_sortie)
                log.info("Sortie %s recotée à %s", t.id, prix)
        etat.maj(s)


def _git_pull(cfg: Config) -> None:
    r = subprocess.run(["git", "-C", str(cfg.tickets_dir), "pull", "--ff-only", "-q"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        log.error("git pull impossible : %s", r.stderr.strip())


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    from ib_async import IB  # import tardif : les tests n'en ont pas besoin

    from .broker import IbBroker

    cfg = Config.depuis_env()
    if not cfg.account_id:
        sys.exit("IB_ACCOUNT_ID est obligatoire")
    notifier = Notifier(cfg.ntfy_url)
    etat = Etat(cfg.state_file)
    ib = IB()
    broker = IbBroker(ib, cfg.account_id)
    notifier(f"Robot démarré ({'SIMULATION' if cfg.dry_run else 'RÉEL'}, compte {cfg.account_id})")
    derniere_erreur = 0.0
    while True:
        try:
            if not ib.isConnected():
                ib.connect(cfg.ib_host, cfg.ib_port, clientId=cfg.ib_client_id, account=cfg.account_id, timeout=20)
                broker.verifier_compte()
                log.info("Connecté à IB Gateway")
            if cfg.git_pull:
                _git_pull(cfg)
            cycle(cfg, broker, etat, notifier, dt.datetime.now(NY))
            ib.sleep(cfg.poll_seconds)
        except KeyboardInterrupt:
            break
        except Exception as e:
            if time.time() - derniere_erreur > 900:  # au plus une alerte d'erreur par quart d'heure
                notifier(f"Erreur du robot : {e!r}", urgent=True)
                derniere_erreur = time.time()
            log.exception("cycle en erreur")
            try:
                ib.disconnect()
            except Exception:
                pass
            time.sleep(30)


if __name__ == "__main__":
    main()
