"""État du robot (SQLite) : ce qui a été envoyé, ouvert, clos. Survit aux redémarrages."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .tickets import Ticket, lire_ticket, ticket_vers_dict

ACTIFS = ("SOUMIS", "OUVERT", "SORTIE_EN_COURS")


@dataclass
class Suivi:
    ticket: Ticket
    statut: str
    cree_le: dt.date
    prix_entree: float | None
    sortie_n: int
    boucles_sortie: int
    motif: str

    @property
    def ref_entree(self) -> str:
        return f"{self.ticket.id}:entree"

    @property
    def ref_tp(self) -> str:
        return f"{self.ticket.id}:tp"

    @property
    def ref_sortie(self) -> str:
        return f"{self.ticket.id}:sortie{self.sortie_n}"


class Etat:
    def __init__(self, chemin: Path):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(chemin))
        self.db.execute("""CREATE TABLE IF NOT EXISTS suivis (
            id TEXT PRIMARY KEY, desk TEXT, run_date TEXT, ticket TEXT, statut TEXT,
            cree_le TEXT, prix_entree REAL, sortie_n INTEGER DEFAULT 0,
            boucles_sortie INTEGER DEFAULT 0, motif TEXT DEFAULT '', maj TEXT)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS erreurs_vues (texte TEXT PRIMARY KEY)")
        self.db.commit()

    def connu(self, tid: str) -> bool:
        return self.db.execute("SELECT 1 FROM suivis WHERE id=?", (tid,)).fetchone() is not None

    def ajouter(self, t: Ticket, statut: str, jour: dt.date, motif: str = "") -> None:
        self.db.execute(
            "INSERT INTO suivis (id, desk, run_date, ticket, statut, cree_le, motif, maj) VALUES (?,?,?,?,?,?,?,?)",
            (t.id, t.desk, t.run_date.isoformat(), json.dumps(ticket_vers_dict(t)), statut,
             jour.isoformat(), motif, dt.datetime.now(dt.timezone.utc).isoformat()))
        self.db.commit()

    def maj(self, s: Suivi) -> None:
        self.db.execute(
            "UPDATE suivis SET statut=?, prix_entree=?, sortie_n=?, boucles_sortie=?, motif=?, maj=? WHERE id=?",
            (s.statut, s.prix_entree, s.sortie_n, s.boucles_sortie, s.motif,
             dt.datetime.now(dt.timezone.utc).isoformat(), s.ticket.id))
        self.db.commit()

    def actifs(self) -> list[Suivi]:
        lignes = self.db.execute(
            f"SELECT desk, run_date, ticket, statut, cree_le, prix_entree, sortie_n, boucles_sortie, motif "
            f"FROM suivis WHERE statut IN ({','.join('?' * len(ACTIFS))})", ACTIFS).fetchall()
        return [Suivi(lire_ticket(json.loads(tk), desk, dt.date.fromisoformat(rd)), st,
                      dt.date.fromisoformat(cl), pe, n, b, m or "")
                for desk, rd, tk, st, cl, pe, n, b, m in lignes]

    def entrees_du_jour(self, jour: dt.date) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM suivis WHERE cree_le=? AND statut NOT IN ('REFUSE')",
            (jour.isoformat(),)).fetchone()[0]

    def premiere_fois(self, erreur: str) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO erreurs_vues (texte) VALUES (?)", (erreur,))
        self.db.commit()
        return cur.rowcount == 1
