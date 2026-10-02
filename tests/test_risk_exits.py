import datetime as dt

from conftest import ticket_dict

from executor.config import Config
from executor.exits import motif_sortie, prix_sortie, valeur_milieu
from executor.risk import refus
from executor.tickets import lire_ticket

CFG = Config()


def test_garde_fous(jour):
    t = lire_ticket(ticket_dict(), "swing", jour)
    assert refus(t, 10_000, 0, 0, set(), CFG) == []
    assert refus(t, 0, 0, 0, set(), CFG) == ["NAV inconnue"]
    assert any("2%" in r for r in refus(t, 5_000, 0, 0, set(), CFG))  # 160 $ > 2 % de 5 000
    assert any("prime" in r for r in refus(t, 9_000, 0, 0, set(), CFG))  # 280 $ > 3 % de 9 000
    assert any("cumulé" in r for r in refus(t, 10_000, 900, 0, set(), CFG))
    assert any("par jour" in r for r in refus(t, 10_000, 0, 3, set(), CFG))
    assert any("déjà" in r for r in refus(t, 10_000, 0, 0, {"SMCI"}, CFG))
    t2 = lire_ticket(ticket_dict(limit_price=3.5), "swing", jour)
    assert any("plafond" in r for r in refus(t2, 10_000, 0, 0, set(), CFG))


def ny(h, mi=0, jour=dt.date(2026, 10, 5)):
    return dt.datetime.combine(jour, dt.time(h, mi))


def test_sorties_debit(jour):
    t = lire_ticket(ticket_dict(), "swing", jour)
    assert motif_sortie(t, 3.0, 43, ny(11)) is None
    assert motif_sortie(t, 1.5, 43, ny(11)) == "SL"
    assert motif_sortie(t, 6.2, 43, ny(11)) == "TP"
    assert motif_sortie(t, 3.0, 37, ny(11)) is None  # stop du sous-jacent jugé à la clôture
    assert motif_sortie(t, 3.0, 37, ny(15, 56)) == "STOP_SOUS_JACENT"
    assert motif_sortie(t, 3.0, 43, ny(10, 5, dt.date(2026, 10, 23))) == "SORTIE_TEMPS"
    assert motif_sortie(t, None, None, ny(11)) is None


def test_sorties_credit(jour):
    t = lire_ticket(ticket_dict(side="SELL", direction="down", limit_price=1.6, price_cap=1.5,
                                take_profit=0.5, stop_loss=3.0, underlying_stop=45), "swing", jour)
    assert motif_sortie(t, 3.1, 40, ny(11)) == "SL"
    assert motif_sortie(t, 0.4, 40, ny(11)) == "TP"
    assert motif_sortie(t, 1.0, 46, ny(15, 58)) == "STOP_SOUS_JACENT"
    assert prix_sortie(t, 1.0, 1.2) == 1.2  # on rachète à l'ask


def test_valeur_milieu():
    assert valeur_milieu(1.0, 1.2) == 1.1
    assert valeur_milieu(None, 1.2) is None
    assert valeur_milieu(1.3, 1.2) is None
