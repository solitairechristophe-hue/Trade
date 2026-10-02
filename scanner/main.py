"""Point d'entrée : `python -m scanner.main --once` (un scan) ou sans option (boucle horaire)."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from zoneinfo import ZoneInfo

from executor.notify import Notifier

from .config import ScanConfig
from .ibkr_nav import nav_et_positions
from .run import scan
from .state import EtatScanner
from .uw_client import UwClient

NY = ZoneInfo("America/New_York")
log = logging.getLogger("scanner")


def un_scan(cfg: ScanConfig, notifier: Notifier, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(NY)
    if cfg.kill_switch_file.exists():
        log.warning("Arrêt d'urgence actif (%s) : scan sans génération de tickets", cfg.kill_switch_file)
    nav, positions, source = nav_et_positions(cfg)
    log.info("NAV %.0f $ (%s), positions : %s", nav, source, ", ".join(sorted(positions)) or "aucune")
    etat = EtatScanner(cfg.state_file)
    feeds = UwClient(cfg)
    res = scan(cfg, feeds, nav, positions, now, etat, ecrire=not cfg.kill_switch_file.exists())
    log.info("%d appels UW, %d candidats étudiés, %d tickets", feeds.appels, len(res.etudies), len(res.tickets))
    if res.tickets:
        lignes = [f"{t['symbol']} {'↑' if t['direction'] == 'up' else '↓'} {t['side']} {t['quantity']}× "
                  f"{t['limit_price']} (TP {t['take_profit']} / SL {t['stop_loss']})" for t in res.tickets]
        notifier(f"Desk Flow {now:%H:%M} : {len(res.tickets)} opportunité(s)\n" + "\n".join(lignes))
    else:
        log.info("Desk Flow %s : aucune opportunité retenue", now.strftime("%H:%M"))
    for e in res.erreurs[:5]:
        log.warning("erreur : %s", e)
    return len(res.tickets)


def prochain_scan(now: dt.datetime, cfg: ScanConfig) -> dt.datetime:
    """Prochain créneau (jours ouvrés, heures de scan, minute fixée)."""
    m = now.replace(second=0, microsecond=0)
    for _ in range(24 * 8):
        m += dt.timedelta(minutes=1)
        if m.weekday() < 5 and m.hour in cfg.scan_hours and m.minute == cfg.scan_minute:
            return m
    return m


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Desk Flow : scanner horaire Unusual Whales → tickets IBKR")
    ap.add_argument("--once", action="store_true", help="un seul scan, puis sortie")
    args = ap.parse_args()
    cfg = ScanConfig.depuis_env()
    if not cfg.uw_token:
        sys.exit("UW_TOKEN est obligatoire (clé API Unusual Whales)")
    notifier = Notifier(cfg.ntfy_url)
    if args.once:
        un_scan(cfg, notifier)
        return
    notifier(f"Scanner Desk Flow démarré (scans à {', '.join(f'{h}h{cfg.scan_minute:02d}' for h in cfg.scan_hours)} NY)")
    while True:
        prochain = prochain_scan(dt.datetime.now(NY), cfg)
        log.info("Prochain scan : %s", prochain.strftime("%Y-%m-%d %H:%M"))
        time.sleep(max(1.0, (prochain - dt.datetime.now(NY)).total_seconds()))
        try:
            un_scan(cfg, notifier, prochain)
        except Exception as e:
            log.exception("scan en erreur")
            notifier(f"Erreur du scanner : {e!r}", urgent=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
