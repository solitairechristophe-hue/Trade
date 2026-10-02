import json

import pytest
from conftest import ticket_dict

from executor.tickets import TicketInvalide, lire_ticket, ticket_vers_dict, tickets_du_jour


def test_lecture_et_aller_retour(jour):
    t = lire_ticket(ticket_dict(), "swing", jour)
    assert t.debit and t.exit_side == "SELL" and t.valid_until == jour
    assert lire_ticket(ticket_vers_dict(t), "swing", jour) == t


@pytest.mark.parametrize("modif", [
    {"side": "HOLD"}, {"quantity": 0}, {"quantity": 1.5}, {"limit_price": -1},
    {"take_profit": 2.5},  # débit avec TP sous la limite
    {"legs": []}, {"legs": [{"expiry": "2026", "strike": 1, "right": "C", "action": "BUY"}]},
    {"condition": {"op": "==", "price": 10}},
])
def test_tickets_invalides(jour, modif):
    with pytest.raises(TicketInvalide):
        lire_ticket(ticket_dict(**modif), "swing", jour)


def test_credit(jour):
    t = lire_ticket(ticket_dict(side="SELL", limit_price=1.6, price_cap=1.5, take_profit=0.5, stop_loss=3.0),
                    "swing", jour)
    assert not t.debit and t.exit_side == "BUY"


def test_dossier(tmp_path, jour):
    (tmp_path / "2026-10-02-swing.json").write_text(json.dumps({"run_date": "2026-10-02", "desk": "swing", "tickets": [
        ticket_dict(), ticket_dict(id="mauvais", side="X")]}))
    (tmp_path / "2026-10-01-swing.json").write_text(json.dumps({"run_date": "2026-10-01", "desk": "swing", "tickets": [
        ticket_dict(id="hier")]}))
    (tmp_path / "casse.json").write_text("{")
    ts, es = tickets_du_jour(tmp_path, jour)
    assert [t.id for t in ts] == ["swing-2026-10-02-SMCI"]  # le ticket d'hier a expiré
    assert len(es) == 2


def test_exemple_documente(jour):
    from pathlib import Path

    from executor.tickets import charger_fichier
    ts, es = charger_fichier(Path(__file__).resolve().parents[1] / "tickets" / "exemple.json.txt")
    assert len(ts) == 1 and es == []
