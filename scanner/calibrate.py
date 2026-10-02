"""Calibration de la probabilité de gain sur l'historique des flow alerts Unusual Whales.

Pour chaque séance passée : prime nette signée par titre (alertes pondérées comme dans le scoring),
direction = signe de la prime nette. Un signal « gagne » si, `hold` séances plus tard, l'action a
bougé dans son sens d'au moins `seuil_atr` × ATR14 (déplacement nécessaire, à peu près, pour qu'un
spread vertical atteigne son take profit). On mesure le taux de gain de tous les signaux (p_min) et
du quintile au plus fort flux (p_max), avec un intervalle de Wilson à 95 %.

Usage : `python -m scanner.calibrate --days 40 --hold 7` (UW_TOKEN requis) ; écrit CALIBRATION_FILE.
C'est une approximation : elle mesure le mouvement de l'action, pas le résultat exact du spread.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

from .model import FlowAlert
from .scoring import poids_alerte

NY = ZoneInfo("America/New_York")
log = logging.getLogger("scanner")


def wilson(gains: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = gains / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(centre - marge, 3), round(centre + marge, 3)


def atr14(bougies: list[dict], i: int) -> float:
    trs = []
    for k in range(max(1, i - 13), i + 1):
        h, l, pc = bougies[k]["high"], bougies[k]["low"], bougies[k - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def signaux_du_jour(alerts: list[FlowAlert], top: int, min_net: float) -> list[tuple[str, int, float]]:
    """(titre, direction ±1, |prime nette|) des `top` titres au plus fort flux net."""
    net: dict[str, float] = defaultdict(float)
    for a in alerts:
        net[a.ticker] += poids_alerte(a) * a.premium * (1 if a.bullish else -1)
    out = [(t, 1 if v > 0 else -1, abs(v)) for t, v in net.items() if abs(v) >= min_net and t.isalpha()]
    return sorted(out, key=lambda x: -x[2])[:top]


def evaluer(signaux: list[tuple[dt.date, str, int, float]], bougies: dict[str, list[dict]], hold: int,
            seuil_atr: float) -> list[tuple[float, bool]]:
    """[(force du signal, gagné)] pour les signaux dont l'issue est connue."""
    res = []
    for jour, t, sens, force in signaux:
        b = bougies.get(t) or []
        idx = next((i for i, c in enumerate(b) if c["date"] == jour), None)
        if idx is None or idx < 15 or idx + hold >= len(b):
            continue
        atr = atr14(b, idx)
        if atr <= 0:
            continue
        mouvement = (b[idx + hold]["close"] - b[idx]["close"]) * sens
        res.append((force, mouvement >= seuil_atr * atr))
    return res


def calibrer(resultats: list[tuple[float, bool]], hold: int, seuil_atr: float, jours: int) -> dict:
    n = len(resultats)
    g = sum(1 for _, w in resultats if w)
    tries = sorted(resultats, key=lambda r: -r[0])
    q = tries[: max(1, n // 5)] if n else []
    gq = sum(1 for _, w in q if w)
    return {
        "p_min": round(g / n, 3) if n else None,
        "p_max": round(gq / len(q), 3) if q else None,
        "n": n, "n_top": len(q),
        "ic95_tous": wilson(g, n), "ic95_top": wilson(gq, len(q)),
        "hold_seances": hold, "seuil_atr": seuil_atr, "jours_analyses": jours,
        "mesure": "mouvement de l'action dans le sens du flux ≥ seuil × ATR14 après hold séances",
        "date": dt.date.today().isoformat(),
    }


def seances_passees(fin: dt.date, n: int) -> list[dt.date]:
    jours, d = [], fin
    while len(jours) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            jours.append(d)
    return sorted(jours)


def lancer(client, jours: int, hold: int, seuil_atr: float, top: int, min_net: float,
           aujourd_hui: dt.date) -> dict:
    signaux: list[tuple[dt.date, str, int, float]] = []
    for j in seances_passees(aujourd_hui, jours + hold):
        if (aujourd_hui - j).days < hold * 7 // 5 + 1:
            continue  # issue pas encore connue
        debut = dt.datetime.combine(j, dt.time(9, 30), NY)
        fin = dt.datetime.combine(j, dt.time(16, 0), NY)
        try:
            alerts = client.flow_alerts(debut, fin, limit=200)
        except Exception as e:
            log.warning("%s : flow alerts indisponibles (%s)", j, e)
            continue
        signaux += [(j, t, s, f) for t, s, f in signaux_du_jour(alerts, top, min_net)]
    bougies = {}
    for t in sorted({s[1] for s in signaux}):
        try:
            bougies[t] = client.daily_candles(t, limit=jours + hold + 40)
        except Exception as e:
            log.warning("%s : bougies indisponibles (%s)", t, e)
    return calibrer(evaluer(signaux, bougies, hold, seuil_atr), hold, seuil_atr, jours)


def main() -> None:
    from pathlib import Path

    from .config import ScanConfig
    from .uw_client import UwClient
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Calibre la probabilité de gain sur l'historique des flow alerts")
    ap.add_argument("--days", type=int, default=40, help="séances de signaux analysées (≤ 2 mois d'historique)")
    ap.add_argument("--hold", type=int, default=7, help="séances de détention")
    ap.add_argument("--seuil-atr", type=float, default=1.0)
    ap.add_argument("--top", type=int, default=10, help="titres retenus par séance")
    ap.add_argument("--min-net", type=float, default=500_000)
    args = ap.parse_args()
    cfg = ScanConfig.depuis_env()
    if not cfg.uw_token:
        sys.exit("UW_TOKEN est obligatoire")
    r = lancer(UwClient(cfg), args.days, args.hold, args.seuil_atr, args.top, args.min_net, dt.date.today())
    Path(cfg.calibration_file).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.calibration_file).write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
