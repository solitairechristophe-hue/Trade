"""Format des tickets publiés par les desks et leur validation.

Un fichier par run : tickets/<AAAA-MM-JJ>-<desk>.json
{
  "run_date": "2026-10-02",
  "desk": "swing",
  "tickets": [ { ... voir Ticket ... } ]
}

Convention des desks : les jambes décrivent le combo dans le sens débit.
Un débit est l'achat du combo (side BUY), un crédit sa vente (side SELL),
toujours à prix positif. TP et SL sont des valeurs du combo.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path


class TicketInvalide(ValueError):
    pass


@dataclass(frozen=True)
class Jambe:
    expiry: str  # AAAAMMJJ
    strike: float
    right: str  # C ou P
    action: str  # BUY ou SELL
    ratio: int = 1


@dataclass(frozen=True)
class Condition:
    """Déclencheur sur le cours de l'action : l'ordre d'entrée ne part qu'une fois franchi."""
    op: str  # ">=" ou "<="
    price: float


@dataclass(frozen=True)
class Ticket:
    id: str
    desk: str
    run_date: dt.date
    symbol: str
    direction: str  # "up" (haussier) ou "down" (baissier)
    side: str  # BUY = débit, SELL = crédit
    quantity: int
    limit_price: float
    price_cap: float
    take_profit: float
    stop_loss: float
    max_loss: float  # perte maximale du trade, en dollars
    premium: float  # prime payée (débit) ou marge bloquée (crédit), en dollars
    legs: tuple[Jambe, ...]
    condition: Condition | None = None
    underlying_stop: float | None = None
    time_exit: dt.date | None = None
    valid_until: dt.date | None = None
    note: str = field(default="", compare=False)

    @property
    def debit(self) -> bool:
        return self.side == "BUY"

    @property
    def exit_side(self) -> str:
        return "SELL" if self.debit else "BUY"


def _date(v, nom: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError as e:
        raise TicketInvalide(f"{nom} : date invalide {v!r}") from e


def _positif(d: dict, nom: str) -> float:
    try:
        v = float(d[nom])
    except (KeyError, TypeError, ValueError) as e:
        raise TicketInvalide(f"{nom} manquant ou non numérique") from e
    if v <= 0:
        raise TicketInvalide(f"{nom} doit être > 0 (reçu {v})")
    return v


def lire_ticket(d: dict, desk: str, run_date: dt.date) -> Ticket:
    tid = str(d.get("id") or "").strip()
    if not tid:
        raise TicketInvalide("id manquant")
    try:
        side = str(d["side"]).upper()
        symbol = str(d["symbol"]).upper().strip()
        direction = str(d["direction"]).lower()
    except KeyError as e:
        raise TicketInvalide(f"{tid} : champ {e} manquant") from e
    if side not in ("BUY", "SELL"):
        raise TicketInvalide(f"{tid} : side doit être BUY ou SELL")
    if direction not in ("up", "down"):
        raise TicketInvalide(f"{tid} : direction doit être up ou down")
    qty = d.get("quantity")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise TicketInvalide(f"{tid} : quantity doit être un entier ≥ 1")

    jambes = []
    for j in d.get("legs") or []:
        try:
            jambe = Jambe(
                expiry=str(j["expiry"]).replace("-", ""),
                strike=float(j["strike"]),
                right=str(j["right"]).upper()[:1],
                action=str(j["action"]).upper(),
                ratio=int(j.get("ratio", 1)),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise TicketInvalide(f"{tid} : jambe invalide {j!r}") from e
        if jambe.right not in ("C", "P") or jambe.action not in ("BUY", "SELL") or jambe.ratio < 1:
            raise TicketInvalide(f"{tid} : jambe invalide {j!r}")
        if len(jambe.expiry) != 8 or not jambe.expiry.isdigit():
            raise TicketInvalide(f"{tid} : échéance invalide {j['expiry']!r}")
        jambes.append(jambe)
    if not 1 <= len(jambes) <= 4:
        raise TicketInvalide(f"{tid} : 1 à 4 jambes attendues")

    cond = None
    if d.get("condition"):
        c = d["condition"]
        op = str(c.get("op", ""))
        if op not in (">=", "<="):
            raise TicketInvalide(f"{tid} : condition.op doit être >= ou <=")
        cond = Condition(op=op, price=_positif(c, "price"))

    t = Ticket(
        id=tid,
        desk=desk,
        run_date=run_date,
        symbol=symbol,
        direction=direction,
        side=side,
        quantity=qty,
        limit_price=_positif(d, "limit_price"),
        price_cap=_positif(d, "price_cap"),
        take_profit=_positif(d, "take_profit"),
        stop_loss=_positif(d, "stop_loss"),
        max_loss=_positif(d, "max_loss"),
        premium=_positif(d, "premium"),
        legs=tuple(jambes),
        condition=cond,
        underlying_stop=float(d["underlying_stop"]) if d.get("underlying_stop") else None,
        time_exit=_date(d.get("time_exit"), f"{tid}.time_exit"),
        valid_until=_date(d.get("valid_until"), f"{tid}.valid_until") or run_date,
        note=str(d.get("note", "")),
    )
    # Cohérence des niveaux de sortie
    if t.debit and not (t.stop_loss < t.limit_price < t.take_profit):
        raise TicketInvalide(f"{tid} : débit attendu avec SL < limite < TP")
    if not t.debit and not (t.take_profit < t.limit_price < t.stop_loss):
        raise TicketInvalide(f"{tid} : crédit attendu avec TP < limite < SL")
    return t


def charger_fichier(chemin: Path) -> tuple[list[Ticket], list[str]]:
    """Renvoie les tickets valides et la liste des erreurs (un ticket invalide n'empêche pas les autres)."""
    erreurs: list[str] = []
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        run_date = dt.date.fromisoformat(doc["run_date"])
        desk = str(doc.get("desk", "desk"))
    except Exception as e:  # fichier illisible : on le signale et on passe
        return [], [f"{chemin.name} : illisible ({e})"]
    tickets = []
    for d in doc.get("tickets") or []:
        try:
            tickets.append(lire_ticket(d, desk, run_date))
        except TicketInvalide as e:
            erreurs.append(f"{chemin.name} : {e}")
    return tickets, erreurs


def tickets_du_jour(dossier: Path, aujourd_hui: dt.date) -> tuple[list[Ticket], list[str]]:
    tickets: list[Ticket] = []
    erreurs: list[str] = []
    vus: set[str] = set()
    for f in sorted(dossier.glob("*.json")):
        ts, es = charger_fichier(f)
        erreurs += es
        for t in ts:
            if t.run_date > aujourd_hui or (t.valid_until and t.valid_until < aujourd_hui):
                continue
            if t.id in vus:
                erreurs.append(f"{f.name} : id en double {t.id}, ignoré")
                continue
            vus.add(t.id)
            tickets.append(t)
    return tickets, erreurs


def ticket_vers_dict(t: Ticket) -> dict:
    """Inverse de lire_ticket : sert à garder le ticket dans l'état du robot."""
    d = {
        "id": t.id, "symbol": t.symbol, "direction": t.direction, "side": t.side,
        "quantity": t.quantity, "limit_price": t.limit_price, "price_cap": t.price_cap,
        "take_profit": t.take_profit, "stop_loss": t.stop_loss, "max_loss": t.max_loss,
        "premium": t.premium, "note": t.note,
        "legs": [{"expiry": j.expiry, "strike": j.strike, "right": j.right,
                  "action": j.action, "ratio": j.ratio} for j in t.legs],
    }
    if t.condition:
        d["condition"] = {"op": t.condition.op, "price": t.condition.price}
    if t.underlying_stop:
        d["underlying_stop"] = t.underlying_stop
    if t.time_exit:
        d["time_exit"] = t.time_exit.isoformat()
    if t.valid_until:
        d["valid_until"] = t.valid_until.isoformat()
    return d
