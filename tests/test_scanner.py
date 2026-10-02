import datetime as dt
import json
import math
from zoneinfo import ZoneInfo

import pytest

from executor.config import Config
from executor.risk import refus
from executor.tickets import tickets_du_jour
from scanner.config import ScanConfig
from scanner.model import FlowAlert, OptionQuote, Regime, ScreenerHit, TickerContext
from scanner.regime import build_regime, tide_bias
from scanner.run import scan
from scanner.scoring import Candidate, noter, regrouper
from scanner.sizing import dimensionner, probabilite
from scanner.state import EtatScanner
from scanner.structure import proposer

NY = ZoneInfo("America/New_York")
JOUR = dt.date(2026, 10, 2)
NOW = dt.datetime(2026, 10, 2, 10, 5, tzinfo=NY)


def alerte(ticker="ACME", type="call", premium=800_000, ask=800_000, bid=0, **k):
    d = dict(ticker=ticker, type=type, premium=premium, size=500, volume=3000, open_interest=800,
             ask_side_premium=ask, bid_side_premium=bid, strike=55, expiry=dt.date(2026, 11, 20),
             underlying_price=50.0, rule="RepeatedHitsAscendingFill", has_sweep=True,
             created_at=NOW - dt.timedelta(minutes=20), sector="Technology", issue_type="Common Stock",
             marketcap=20e9)
    d.update(k)
    return FlowAlert(**d)


def _N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs(S, K, T, iv, call):
    """Black-Scholes sans taux : (prix, delta) — cotations synthétiques cohérentes avec les deltas."""
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if call:
        return S * _N(d1) - K * _N(d2), _N(d1)
    return K * _N(-d2) - S * _N(-d1), _N(d1) - 1


def chaine(prix=50.0, expiry=dt.date(2026, 11, 20), largeur_pas=1.0, iv=0.45):
    """Chaîne synthétique (calls et puts) cotée par Black-Scholes, spread 0,08."""
    q = []
    T = max((expiry - JOUR).days, 1) / 365
    for i in range(-10, 11):
        k = round(prix + i * largeur_pas, 2)
        for typ, call in (("call", True), ("put", False)):
            val, delta = _bs(prix, k, T, iv, call)
            val = max(val, 0.05)
            q.append(OptionQuote(f"ACME{expiry:%y%m%d}{'C' if call else 'P'}{int(k * 1000):08d}", typ, k, expiry,
                                 round(val - 0.01, 2), round(val + 0.01, 2), round(delta, 3), 500, 300, iv))
    return q


def contexte(**k):
    c = TickerContext(ticker="ACME", price=50.0, atr14=1.2, sma20=48.0, sma50=46.0, avg_volume=5e6,
                      sector="Technology", marketcap=20e9, iv_rank=0.30, call_wall=55.0, put_wall=47.0,
                      net_call_premium=2e6, net_put_premium=-0.5e6, gex_net=-1e6, chain=chaine())
    for a, v in k.items():
        setattr(c, a, v)
    return c


class FauxFeeds:
    def __init__(self, alerts=None, ctx=None, tide=None, events=None):
        self._alerts = alerts if alerts is not None else [alerte(), alerte(premium=400_000, ask=400_000)]
        self._ctx = ctx or {"ACME": contexte()}
        self._tide = tide or [{"net_call_premium": 0, "net_put_premium": 0}] + \
            [{"net_call_premium": 5e6 * i, "net_put_premium": -2e6 * i} for i in range(1, 13)]
        self._events = events or []

    def market_tide(self):
        return self._tide

    def sector_tides(self):
        return {"Technology": self._tide}

    def spy_gex_net(self):
        return 1.5e9

    def economic_calendar(self):
        return self._events

    def flow_alerts(self, newer_than):
        return self._alerts

    def screener_hits(self):
        return [ScreenerHit("ACME", "Unusually Bullish", True, 300_000, 50.0)]

    def dark_pool_recent(self):
        return []

    def market_oi_changes(self):
        return []

    def insider_recent(self):
        return []

    def congress_recent(self):
        return []

    def enrich(self, ticker, today, min_dte, max_dte):
        return self._ctx[ticker]


def cfg_test(tmp_path, **k):
    base = dict(tickets_dir=tmp_path / "tickets", reports_dir=tmp_path / "reports",
                state_file=tmp_path / "scanner.sqlite", kill_switch_file=tmp_path / "STOP", nav_usd=8918.0,
                calibration_file=tmp_path / "calibration.json")
    base.update(k)
    return ScanConfig(**base)


# --- régime ------------------------------------------------------------------------

def test_tide_bias_signe():
    hausse = [{"net_call_premium": 0, "net_put_premium": 0}, {"net_call_premium": 40e6, "net_put_premium": -10e6}]
    baisse = [{"net_call_premium": 0, "net_put_premium": 0}, {"net_call_premium": -40e6, "net_put_premium": 30e6}]
    assert tide_bias(hausse) > 0.5 and tide_bias(baisse) < -0.5
    assert tide_bias([]) == 0.0


def test_regime_risk_off_sur_evenement():
    ev = [{"event": "FOMC", "time": (NOW + dt.timedelta(minutes=30)).isoformat()}]
    r = build_regime([], {}, -1e9, ev, NOW)
    assert r.risk_off and r.spy_gex_positive is False and "FOMC" in r.events_soon[0]


# --- scoring -----------------------------------------------------------------------

def test_scoring_direction_et_confluence():
    c = regrouper([alerte(), alerte(premium=400_000, ask=400_000)], [ScreenerHit("ACME", "Unusually Bullish", True)],
                  [], [], [], [])["ACME"]
    c.context = contexte()
    noter(c, Regime(bias=0.5), JOUR, 50)
    assert c.direction == "up" and c.score > 65
    assert c.factors["flow"] > 0.5 and c.factors["regime"] > 0

    # même flux, puts achetés : baissier ; régime haussier en désaccord → score plus bas
    b = regrouper([alerte(type="put"), alerte(type="put", premium=400_000, ask=400_000)], [], [], [], [], [])["ACME"]
    b.context = contexte(sma20=52.0, sma50=53.0)
    noter(b, Regime(bias=0.5), JOUR, 50)
    assert b.direction == "down" and b.factors["regime"] < 0 and b.score < c.score


def test_scoring_penalise_resultats_proches():
    c = regrouper([alerte()], [], [], [], [], [])["ACME"]
    c.context = contexte(next_earnings=JOUR + dt.timedelta(days=2))
    noter(c, Regime(), JOUR, 50)
    assert c.factors["earnings"] == -1.0


# --- structure ---------------------------------------------------------------------

def test_vertical_debit_haussier():
    p = proposer(contexte(), "up", JOUR, min_dte=21, max_dte=50, max_premium=267.0)
    assert p is not None and p.side == "BUY" and p.strategy == "bull call spread"
    assert p.legs[0]["action"] == "BUY" and p.legs[1]["action"] == "SELL"
    assert p.legs[0]["strike"] < p.legs[1]["strike"]
    assert p.stop_loss < p.limit_price < p.take_profit <= p.width
    assert p.premium_per_contract <= 267.0
    assert p.condition == {"op": ">=", "price": round(50 + 0.15 * 1.2, 2)}
    assert p.underlying_stop < 50 and p.time_exit == dt.date(2026, 10, 12)  # J+10, avant échéance − 7 j


def test_vertical_credit_quand_iv_riche():
    p = proposer(contexte(iv_rank=0.80), "up", JOUR, min_dte=21, max_dte=50, max_premium=267.0)
    assert p is not None and p.side == "SELL" and p.strategy == "bull put spread"
    assert p.legs[0]["right"] == "P" and p.legs[0]["strike"] > p.legs[1]["strike"]
    assert p.take_profit < p.limit_price < p.stop_loss


def test_structure_evite_les_resultats():
    ctx = contexte(next_earnings=dt.date(2026, 11, 5))
    assert proposer(ctx, "up", JOUR, min_dte=21, max_dte=50) is None  # seule échéance enjambe les résultats
    ctx2 = contexte(next_earnings=dt.date(2026, 11, 5), chain=chaine() + chaine(expiry=dt.date(2026, 10, 30)))
    p = proposer(ctx2, "up", JOUR, min_dte=21, max_dte=50)
    assert p is not None and p.expiry == dt.date(2026, 10, 30)


def test_structure_trop_chere_refusee():
    assert proposer(contexte(), "up", JOUR, min_dte=21, max_dte=50, max_premium=20.0) is None


# --- sizing ------------------------------------------------------------------------

def test_sizing_respecte_les_garde_fous():
    p = proposer(contexte(), "up", JOUR, min_dte=21, max_dte=50, max_premium=267.0)
    d = dimensionner(p, 75.0, 8918.0, risk_per_trade=0.02, max_premium_per_trade=0.03, max_contracts=5,
                     risque_restant=891.0)
    assert d is not None and 1 <= d.quantity <= 5
    assert d.max_loss <= 8918 * 0.02 and d.premium <= 8918 * 0.03
    assert 0.38 <= d.p_win <= 0.62 and probabilite(200) == 0.62
    assert dimensionner(p, 75.0, 500.0, risk_per_trade=0.02, max_premium_per_trade=0.03, max_contracts=5,
                        risque_restant=50.0) is None


# --- scan complet ------------------------------------------------------------------

def test_scan_produit_un_ticket_accepte_par_le_robot(tmp_path):
    cfg = cfg_test(tmp_path)
    etat = EtatScanner(cfg.state_file)
    res = scan(cfg, FauxFeeds(), 8918.0, set(), NOW, etat)
    assert len(res.retenus) == 1 and res.tickets[0]["id"] == "flow-2026-10-02-ACME"
    assert res.feeds["flow alerts"].startswith("ok")
    assert "ACME" in res.rapport and "RETENU #1" in res.rapport

    # le fichier est relu par le robot, et ses garde-fous l'acceptent
    tickets, erreurs = tickets_du_jour(cfg.tickets_dir, JOUR)
    assert erreurs == [] and len(tickets) == 1
    t = tickets[0]
    assert refus(t, 8918.0, 0.0, 0, set(), Config()) == []
    assert (cfg.reports_dir / "2026-10-02-1005-flow.md").exists() and (cfg.reports_dir / "dernier-flow.md").exists()

    # deuxième scan de l'heure suivante : délai de carence, pas de doublon
    res2 = scan(cfg, FauxFeeds(), 8918.0, set(), NOW + dt.timedelta(hours=1), etat)
    assert res2.retenus == []
    doc = json.loads((cfg.tickets_dir / "2026-10-02-flow.json").read_text())
    assert len(doc["tickets"]) == 1


def test_scan_exclut_positions_et_risk_off(tmp_path):
    cfg = cfg_test(tmp_path)
    assert scan(cfg, FauxFeeds(), 8918.0, {"ACME"}, NOW, ecrire=False).retenus == []
    ev = [{"event": "CPI", "time": (NOW + dt.timedelta(minutes=45)).isoformat()}]
    res = scan(cfg, FauxFeeds(events=ev), 8918.0, set(), NOW, ecrire=False)
    assert res.retenus == [] and res.regime.risk_off


def test_scan_sans_nav_ne_produit_rien(tmp_path):
    cfg = cfg_test(tmp_path, nav_usd=0.0)
    res = scan(cfg, FauxFeeds(), 0.0, set(), NOW, ecrire=False)
    assert res.retenus == [] and any("NAV" in e for e in res.erreurs)


def test_scan_survit_a_un_flux_en_panne(tmp_path):
    class Panne(FauxFeeds):
        def dark_pool_recent(self):
            raise RuntimeError("503")
    res = scan(cfg_test(tmp_path), Panne(), 8918.0, set(), NOW, ecrire=False)
    assert res.feeds["dark pool recent"].startswith("échec") and len(res.retenus) == 1


def test_quota_journalier(tmp_path):
    cfg = cfg_test(tmp_path, max_new_orders_per_day=1)
    etat = EtatScanner(cfg.state_file)
    etat.enregistrer("flow-2026-10-02-XYZ", "XYZ", "up", NOW - dt.timedelta(hours=1), 70, 10, 1, "")
    res = scan(cfg, FauxFeeds(), 8918.0, set(), NOW, etat, ecrire=False)
    assert res.retenus == [] and any("hors quota" in d for _, d in res.etudies)


def test_evenement_mineur_non_risk_off():
    ev = [{"event": "Factory Orders", "time": (NOW + dt.timedelta(minutes=30)).isoformat()}]
    assert not build_regime([], {}, 1e9, ev, NOW).risk_off


def test_debit_se_resserre_quand_la_prime_depasse_le_budget():
    large = proposer(contexte(), "up", JOUR, min_dte=21, max_dte=50, max_premium=1e9)
    etroit = proposer(contexte(), "up", JOUR, min_dte=21, max_dte=50, max_premium=80.0)
    assert large is not None and etroit is not None
    assert etroit.premium_per_contract <= 80.0 < large.premium_per_contract
    assert etroit.width < large.width and etroit.width >= 0.5 * 1.2


def test_credit_a_esperance_positive():
    p = proposer(contexte(iv_rank=0.80), "up", JOUR, min_dte=21, max_dte=50, max_premium=400.0)
    d = dimensionner(p, 65.0, 8918.0, risk_per_trade=0.02, max_premium_per_trade=0.03, max_contracts=5,
                     risque_restant=891.0)
    assert d is not None and d.ev > 0


# --- horizon, liquidité, flux lié aux résultats, calibration ---------------------

def test_sortie_temps_horizon_court():
    from scanner.structure import sortie_temps
    assert sortie_temps(JOUR, dt.date(2026, 11, 20), 10) == dt.date(2026, 10, 12)
    assert sortie_temps(JOUR, dt.date(2026, 10, 16), 10) == dt.date(2026, 10, 9)


def test_flux_avant_resultats_compte_moitie():
    from scanner.scoring import poids_alerte
    assert poids_alerte(alerte(next_earnings=dt.date(2026, 11, 15))) == 0.5  # échéance 20/11, 5 j après
    assert poids_alerte(alerte(next_earnings=dt.date(2026, 12, 15))) == 1.0
    assert poids_alerte(alerte()) == 1.0


def test_liquidite_relative():
    from scanner.scoring import facteur_liquidite
    liquide = contexte(options_volume=60_000, stock_volume=2_000_000, marketcap=20e9)  # O/S 3
    lourd = contexte(options_volume=50_000, stock_volume=80_000_000, marketcap=3000e9)  # O/S 0,06, méga-cap
    assert facteur_liquidite(liquide) > 0.9 and facteur_liquidite(lourd) < -0.5


def test_calibration(tmp_path):
    from scanner.calibrate import calibrer, evaluer, signaux_du_jour, wilson
    from scanner.sizing import charger_calibration, probabilite
    sig = signaux_du_jour([alerte(), alerte(ticker="BAD", type="put", premium=900_000, ask=900_000)], 10, 100_000)
    assert ("ACME", 1, 800_000) in sig and sig[0][0] == "BAD" and sig[0][1] == -1
    jours = [dt.date(2026, 8, 1) + dt.timedelta(days=i) for i in range(30)]
    hausse = [{"date": d, "open": 50 + i, "high": 51 + i, "low": 49 + i, "close": 50 + i} for i, d in enumerate(jours)]
    plat = [{"date": d, "open": 50, "high": 51, "low": 49, "close": 50} for d in jours]
    r = evaluer([(jours[20], "UP", 1, 2.0), (jours[20], "FLAT", 1, 1.0), (jours[29], "UP", 1, 1.0)],
                {"UP": hausse, "FLAT": plat}, hold=5, seuil_atr=1.0)
    assert r == [(2.0, True), (1.0, False)]  # le dernier signal n'a pas encore d'issue
    c = calibrer(r, 5, 1.0, 20)
    assert c["p_min"] == 0.5 and c["p_max"] == 1.0 and c["n"] == 2
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi
    f = tmp_path / "calibration.json"
    f.write_text(json.dumps(c))
    assert charger_calibration(f) == (0.5, 0.7)  # borné à 0,70
    assert probabilite(100, (0.5, 0.7)) == 0.7 and probabilite(0) == 0.38
    assert charger_calibration(tmp_path / "absent.json") is None


def test_calibration_sans_avantage_bloque_les_trades(tmp_path):
    cfg = cfg_test(tmp_path)
    cfg.calibration_file.write_text(json.dumps({"p_min": 0.243, "p_max": 0.259}))
    res = scan(cfg, FauxFeeds(), 8918.0, set(), NOW, ecrire=False)
    assert res.retenus == [] and any("espérance négative" in d for _, d in res.etudies)
    assert res.feeds["calibration de p"].startswith("0.30")


# --- règles issues du backtest croisé -----------------------------------------------

def test_murs_gamma_contre_le_trade_rejete(tmp_path):
    from scanner.scoring import murs_contre, setup_gamma
    bute = contexte(call_wall=50.3, put_wall=44.0)  # call wall à 0,25 ATR au-dessus : la hausse bute
    assert murs_contre(bute, 1) and not setup_gamma(bute, 1)
    assert setup_gamma(contexte(), 1) and not murs_contre(contexte(), 1)
    res = scan(cfg_test(tmp_path), FauxFeeds(ctx={"ACME": bute}), 8918.0, set(), NOW, ecrire=False)
    assert res.retenus == [] and any("mur gamma" in d for _, d in res.etudies)


def test_sans_gamma_negatif_pas_de_trade(tmp_path):
    res = scan(cfg_test(tmp_path), FauxFeeds(ctx={"ACME": contexte(gex_net=2e6)}), 8918.0, set(), NOW, ecrire=False)
    assert res.retenus == [] and any("pas de setup gamma" in d for _, d in res.etudies)
    res2 = scan(cfg_test(tmp_path, require_gamma_setup=False), FauxFeeds(ctx={"ACME": contexte(gex_net=2e6)}),
                8918.0, set(), NOW, ecrire=False)
    assert len(res2.retenus) == 1


def test_esperance_mesuree_et_taille_essai(tmp_path):
    cfg = cfg_test(tmp_path)
    cfg.calibration_file.write_text(json.dumps({"p_min": 0.243, "p_max": 0.259,
                                                "setups": {"gamma": {"rendement_moyen": 0.029}}}))
    res = scan(cfg, FauxFeeds(), 8918.0, set(), NOW, ecrire=False)
    assert len(res.retenus) == 1
    d = res.retenus[0]
    assert d.quantity == 1 and d.ev == round(0.029 * d.prop.premium_per_contract, 2)
    assert d.prop.price_cap == d.prop.limit_price  # entrée au mid, sans poursuite


def test_spread_trop_large_refuse():
    large = contexte(chain=[OptionQuote(q.symbol, q.type, q.strike, q.expiry, q.bid - 0.10, q.ask + 0.10, q.delta,
                                        q.open_interest, q.volume, q.iv) for q in chaine()])
    assert proposer(large, "up", JOUR, min_dte=21, max_dte=50) is None
