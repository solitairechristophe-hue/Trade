"""État du scanner (SQLite) : tickets déjà proposés (anti-doublon, délai de carence) et journal des runs."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path


class EtatScanner:
    def __init__(self, chemin: Path):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(chemin))
        self.db.execute("""CREATE TABLE IF NOT EXISTS propositions (
            id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, jour TEXT, heure TEXT,
            score REAL, ev REAL, quantity INTEGER, note TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
            quand TEXT PRIMARY KEY, candidats INTEGER, tickets INTEGER, erreurs TEXT)""")
        self.db.commit()

    def symboles_recents(self, jour: dt.date, carence_jours: int) -> set[str]:
        depuis = (jour - dt.timedelta(days=carence_jours)).isoformat()
        return {r[0] for r in self.db.execute("SELECT symbol FROM propositions WHERE jour >= ?", (depuis,))}

    def tickets_du_jour(self, jour: dt.date) -> int:
        return self.db.execute("SELECT COUNT(*) FROM propositions WHERE jour=?", (jour.isoformat(),)).fetchone()[0]

    def enregistrer(self, tid: str, symbol: str, direction: str, quand: dt.datetime, score: float, ev: float,
                    quantity: int, note: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO propositions VALUES (?,?,?,?,?,?,?,?,?)",
                        (tid, symbol, direction, quand.date().isoformat(), quand.isoformat(), score, ev, quantity, note))
        self.db.commit()

    def journal(self, quand: dt.datetime, candidats: int, tickets: int, erreurs: list[str]) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?)",
                        (quand.isoformat(), candidats, tickets, "; ".join(erreurs)[:2000]))
        self.db.commit()
