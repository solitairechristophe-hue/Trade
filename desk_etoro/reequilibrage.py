"""Revue hebdomadaire : écart entre le portefeuille du desk de la semaine passée et la nouvelle cible.

L'état (data/desk_etoro/etat.json) garde la dernière cible publiée. Les ordres sont proposés,
jamais transmis : chaque ordre eToro se passe ensuite avec prepare-trade / place-trade (ou à la main),
après validation. Chez eToro le levier est attaché à la position : changer de levier = clôturer
puis rouvrir.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .allocation import PortefeuilleCible

ORDRE_AFFICHAGE = {"VENTE": 0, "CHANGER LEVIER": 1, "ALLÉGER": 2, "ACHAT": 3, "RENFORCER": 4, "CONSERVER": 5}


@dataclass
class Ordre:
    action: str
    instrument_id: int
    symbol: str
    poids_avant: float
    poids_apres: float
    levier_avant: int
    levier_apres: int
    montant: float  # variation de la marge engagée (devise du compte), négative = à retirer
    exposition_apres: float  # montant exposé après l'ordre (marge × levier)
    stop: float | None = None


def lire_etat(chemin: Path) -> dict:
    if not chemin.exists():
        return {"date": None, "lignes": {}}
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire_etat(chemin: Path, date: str, cible: PortefeuilleCible) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    etat = {"date": date, "cash": round(cible.cash, 6), "lignes": {
        str(l.instrument_id): {"symbol": l.symbol, "poids": round(l.poids, 6), "levier": l.levier,
                               "stop": l.stop, "score": round(l.score, 2)} for l in cible.lignes}}
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


def poids_detenus(etat: dict) -> dict[int, float]:
    return {int(k): float(v.get("poids") or 0) for k, v in (etat.get("lignes") or {}).items()}


def ordres(etat: dict, cible: PortefeuilleCible, capital: float, bande: float) -> list[Ordre]:
    avant = {int(k): v for k, v in (etat.get("lignes") or {}).items()}
    apres = {l.instrument_id: l for l in cible.lignes}
    out: list[Ordre] = []
    for iid in sorted(set(avant) | set(apres)):
        a, n = avant.get(iid), apres.get(iid)
        pa, la = (float(a["poids"]), int(a.get("levier") or 1)) if a else (0.0, 1)
        pn, ln = (n.poids, n.levier) if n else (0.0, 1)
        symbol = n.symbol if n else a.get("symbol", str(iid))
        if a is None:
            action = "ACHAT"
        elif n is None:
            action = "VENTE"
        elif ln != la:
            action = "CHANGER LEVIER"
        elif pn - pa >= bande:
            action = "RENFORCER"
        elif pa - pn >= bande:
            action = "ALLÉGER"
        else:
            action = "CONSERVER"
        delta = pn - pa if action != "CONSERVER" else 0.0
        out.append(Ordre(action, iid, symbol, round(pa, 6), round(pn, 6), la, ln, round(delta * capital, 2),
                         round(pn * ln * capital, 2), n.stop if n else None))
    out.sort(key=lambda o: (ORDRE_AFFICHAGE[o.action], -abs(o.montant)))
    return out


def en_dicts(liste: list[Ordre]) -> list[dict]:
    return [asdict(o) for o in liste]
