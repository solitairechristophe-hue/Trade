import datetime as dt
import json

import pytest

from desk_etoro import allocation, calendrier, composition, metriques, qualite, reequilibrage, tickers
from desk_etoro.allocation import LigneCible, Risque
from desk_etoro.client import ClientEtoro, ErreurApi, Limiteur, lire_reponse_mcp
from desk_etoro.config import Allocation, Config, Connexion, Qualite, Tickers, Univers
from desk_etoro.qualite import NotePortefeuille
from desk_etoro.sources import Collecteur, Snapshot

JOUR = dt.date(2026, 10, 2)


# -- Métriques ------------------------------------------------------------------------------
def test_metriques_de_base():
    r = [0.10, -0.05, 0.02, 0.03, -0.10, 0.04]
    assert metriques.rendement_cumule(r) == pytest.approx(1.1 * 0.95 * 1.02 * 1.03 * 0.9 * 1.04 - 1)
    # pire recul : du pic 1.1 au creux 1.1*0.95*1.02*1.03*0.9
    assert metriques.drawdown_max(r) == pytest.approx(0.95 * 1.02 * 1.03 * 0.9 - 1)
    assert metriques.part_positive(r) == pytest.approx(4 / 6)
    assert metriques.sharpe(r, 12) is not None
    assert metriques.sortino([0.01] * 6, 12) is None  # aucune baisse
    assert metriques.volatilite([0.01, 0.02], 12) is None  # trop court


def test_stabilite_et_calmar():
    regulier = [0.01] * 24
    heurte = [0.08, -0.06] * 12
    assert metriques.stabilite(regulier) == pytest.approx(1.0)
    assert metriques.stabilite(heurte) < 0.9
    assert metriques.stabilite([-0.01] * 12) == 0.0
    assert metriques.calmar([0.02, -0.01] * 6, 12) > 0


def test_rang_percentile_ex_aequo_et_absents():
    r = metriques.rang_percentile({"a": 1, "b": 2, "c": 2, "d": None, "e": 3})
    assert r == {"a": 0.0, "b": 0.5, "c": 0.5, "e": 1.0}
    assert metriques.rang_percentile({"a": 1, "b": 5}, plus_haut_mieux=False) == {"b": 0.0, "a": 1.0}


# -- Composition ----------------------------------------------------------------------------
def live(positions, copies=()):
    return {"positions": list(positions), "socialTrades": list(copies)}


def pos(iid, inv, pnl=0.0, buy=True, lev=1, ouverture="2025-01-10T10:00:00Z"):
    return {"instrumentId": iid, "investmentPct": inv, "netProfit": pnl, "isBuy": buy, "leverage": lev,
            "openTimestamp": ouverture}


def test_composition_live_poids_et_signaux():
    c = composition.analyser(live([
        pos(1, 40, pnl=50),  # vaut 60
        pos(1, 10, pnl=0, ouverture="2026-09-25T10:00:00Z"),  # 10, récente
        pos(2, 30, pnl=-50, buy=False),  # vaut 15, vendeuse
        pos(3, 10, pnl=0, lev=2),  # 10, à levier
    ]), JOUR)  # 10 % de liquidités
    total = 60 + 10 + 15 + 10 + 10
    assert c.lignes[1].poids_long == pytest.approx(70 / total)
    assert c.lignes[1].poids_recent == pytest.approx(10 / total)
    assert c.lignes[2].poids_court == pytest.approx(15 / total)
    assert c.lignes[2].poids_net == pytest.approx(-15 / total)
    assert c.lignes[3].poids_levier == pytest.approx(10 / total)
    assert c.part_investie == pytest.approx(95 / total)
    assert c.part_positions_gagnantes == pytest.approx(1 / 4)
    assert c.nb_lignes_effectif == pytest.approx(1 / ((70 / 95) ** 2 + (15 / 95) ** 2 + (10 / 95) ** 2))


def test_composition_copies():
    copie = {"investmentPct": 50, "openInvestmentPct": 50, "netProfit": 0, "openNetProfit": 0,
             "positions": [pos(7, 5), pos(8, 15)]}
    sans = composition.analyser(live([pos(1, 50)], [copie]), JOUR)
    assert set(sans.lignes) == {1} and sans.part_copies == pytest.approx(0.5)
    avec = composition.analyser(live([pos(1, 50)], [copie]), JOUR, inclure_copies=True)
    assert avec.lignes[7].poids == pytest.approx(0.125) and avec.lignes[8].poids == pytest.approx(0.375)


def test_composition_actifs_et_renforcement():
    rep = {"results": [
        {"date": "2026-09-01", "assets": [{"instrumentId": 1, "investedPct": 0.30, "valuePct": 0.30},
                                          {"instrumentId": 2, "investedPct": 0.20, "valuePct": 0.20}]},
        {"date": "2026-10-01", "assets": [{"instrumentId": 1, "investedPct": 0.30, "valuePct": 0.35},
                                          {"instrumentId": 2, "investedPct": 0.40, "valuePct": 0.40},
                                          {"instrumentId": 3, "investedPct": 0.20, "valuePct": 0.20},
                                          {"instrumentId": 4, "investedPct": 0.05, "valuePct": 0.0}]},
    ]}
    c = composition.depuis_actifs(rep, 30)
    assert set(c.lignes) == {1, 2, 3}  # valeur nulle ignorée
    assert c.lignes[1].poids_recent == 0.0
    assert c.lignes[2].poids_recent == pytest.approx(0.40 * 0.5)
    assert c.lignes[3].poids_recent == pytest.approx(0.20)
    assert c.source == "actifs+historique"


def test_fusion_des_cotations():
    from desk_etoro.desk import alias_de_cotation
    alias = alias_de_cotation({1: {"symbol": "AMZN"}, 2: {"symbol": "AMZN.RTH"}, 3: {"symbol": "XYZ.RTH"},
                               4: {"symbol": "GOOG"}, 5: {"symbol": "GOOGL"}, 6: {"symbol": "GOOGL.RTH"}}, {"GOOGL": "GOOG"})
    assert alias == {2: 1, 5: 4, 6: 4}
    c = composition.analyser(live([pos(1, 20), pos(2, 30, ouverture="2026-09-30T10:00:00Z")]), JOUR)
    c.fusionner(alias)
    assert set(c.lignes) == {1} and c.lignes[1].poids == pytest.approx(0.5)
    assert c.lignes[1].poids_recent == pytest.approx(0.3) and c.lignes[1].nb_positions == 2


# -- Qualité -----------------------------------------------------------------------------------
def ligne_classement(nom, **k):
    l = {"username": nom, "type": "trader", "subType": "pi-elite", "gain": 0.2, "riskScore": 4,
         "maxMonthlyRiskScore": 5, "maxDailyRiskScore": 5, "weeksSinceRegistration": 200, "activeWeeksPct": 100,
         "exposure": 90, "highLeveragePct": 0, "annualizedReturn": 0.15, "peakToValley": -15, "dailyDD": -3,
         "weeklyDD": -6, "profitableMonthsPct": 60, "profitableWeeksPct": 55, "winRatio": 60, "copiers": 100,
         "copiersGain": 0.01, "aumValue": 1e6}
    l.update(k)
    return l


def test_filtres_univers():
    u = Univers()
    assert qualite.motif_exclusion(ligne_classement("a"), u) is None
    assert qualite.motif_exclusion(ligne_classement("a", riskScore=8), u).startswith("risque")
    assert qualite.motif_exclusion(ligne_classement("a", riskScore=0), u) == "pas de score de risque"
    assert qualite.motif_exclusion(ligne_classement("a", gain=-1.0), u) == "inactif ou sans historique"
    assert qualite.motif_exclusion(ligne_classement("a", weeksSinceRegistration=10), u) == "historique trop court"
    assert qualite.motif_exclusion(ligne_classement("a", exposure=5), u) == "trop peu investi"
    assert qualite.motif_exclusion(ligne_classement("a", subType="pi-elite"), Univers(paliers_admis=("pi-elite-pro",)))


def note(nom, rendements, comp=None, **k):
    l = ligne_classement(nom, **k)
    return NotePortefeuille(nom, l, qualite.extraire(l, {}, rendements, comp, 0.0), composition=comp)


def test_noter_classe_le_meilleur_devant_et_quantile():
    bon = note("bon", [0.02, 0.01, 0.03, 0.01, 0.02, 0.01] * 3, gain=0.4, riskScore=3, peakToValley=-8, copiers=5000)
    moyen = note("moyen", [0.03, -0.02, 0.02, -0.01, 0.01, 0.0] * 3)
    faible = note("faible", [0.08, -0.09, 0.05, -0.07, 0.02, -0.03] * 3, gain=-0.1, riskScore=6, peakToValley=-40,
                  copiers=3)
    notes = [faible, moyen, bon]
    qualite.noter(notes, Qualite(quantile_min=0.34))
    assert bon.qualite > moyen.qualite > faible.qualite
    assert faible.vote == 0.0 and bon.vote == pytest.approx(bon.qualite ** 2)


# -- Tickers -------------------------------------------------------------------------------------
def portefeuille(nom, q, lignes, recents=()):
    comp = composition.Composition()
    for iid, w in lignes.items():
        comp.lignes[iid] = composition.Ligne(iid, poids_long=w, poids_recent=w if iid in recents else 0.0)
    n = NotePortefeuille(nom, {"username": nom}, composition=comp)
    n.qualite, n.vote = q, q ** 2
    return n


def test_croisement_tickers():
    ps = [portefeuille("a", 0.9, {1: 0.5, 2: 0.2}, recents={2}),
          portefeuille("b", 0.6, {1: 0.3, 3: 0.4}),
          portefeuille("c", 0.3, {1: 0.1, 2: 0.1, 3: 0.1}),
          portefeuille("d", 0.8, {2: 0.3, 3: 0.2})]
    notes = tickers.noter(ps, Tickers(detenteurs_min=3))
    par = {t.instrument_id: t for t in notes}
    total = sum(p.vote for p in ps)
    t1 = par[1]
    assert t1.nb_detenteurs == 3
    assert t1.consensus == pytest.approx((0.81 * 0.5 + 0.36 * 0.3 + 0.09 * 0.1) / total)
    assert t1.largeur == pytest.approx((0.81 + 0.36 + 0.09) / total)
    assert t1.conviction == pytest.approx((0.81 * 0.5 + 0.36 * 0.3 + 0.09 * 0.1) / (0.81 + 0.36 + 0.09))
    assert par[2].fraicheur > 0 and par[3].fraicheur == 0
    assert [t.rang for t in notes] == [1, 2, 3]
    assert all(0 <= t.score <= 100 for t in notes)
    assert tickers.noter(ps, Tickers(detenteurs_min=4)) == []


# -- Allocation ------------------------------------------------------------------------------------
def test_repartir_plafond_plancher():
    w = allocation._repartir({1: 10, 2: 1, 3: 1, 4: 1}, 0.9, 0.4, 0.1)
    assert w[1] == pytest.approx(0.4)
    assert sum(w.values()) == pytest.approx(0.9)
    assert min(w.values()) >= 0.1 - 1e-9


def lc(iid, score, classe="stocks", vol=0.25, cours=100.0):
    return LigneCible(iid, f"T{iid}", "", classe, score, 1, vol=vol, cours=cours)


def test_ponderer_plafond_crypto():
    cfg = Allocation(poids_max=0.30, poids_min=0.02, poids_max_crypto=0.15, reserve_cash=0.0)
    lignes = [lc(1, 95, "crypto", vol=0.6), lc(2, 90, "crypto", vol=0.6), lc(3, 70), lc(4, 65), lc(5, 60)]
    cash = allocation.ponderer(lignes, cfg)
    assert sum(l.poids for l in lignes if l.classe == "crypto") == pytest.approx(0.15)
    assert cash == pytest.approx(0.0, abs=1e-9)
    assert max(l.poids for l in lignes) <= 0.30 + 1e-9


def elig(leviers=(1, 2, 5), ouverture=True):
    return {"allowOpenPosition": ouverture, "leverageConfigs": [
        {"direction": "LONG", "leverageValues": list(leviers), "isPotential": False,
         "minStopLossPercentage": 5.0, "maxStopLossPercentage": 50.0}]}


def test_levier_conditions():
    cfg = Allocation()
    haussier = Risque(dernier=110, vol=0.20, mm50=100, mm200=90, recul_52s=-0.05)
    l = lc(1, 90, vol=0.20, cours=110)
    allocation.appliquer_levier(l, elig(), haussier, cfg)
    assert l.levier == 2  # x5 exclu par levier_max
    l2 = lc(2, 70, vol=0.20)
    allocation.appliquer_levier(l2, elig(), haussier, cfg)
    assert l2.levier == 1 and "score" in l2.motif_levier
    l2b = lc(7, 95, vol=0.20)
    l2b.rang = 11
    allocation.appliquer_levier(l2b, elig(), haussier, cfg)
    assert l2b.levier == 1 and "rang" in l2b.motif_levier
    l3 = lc(3, 90, vol=0.30)
    allocation.appliquer_levier(l3, elig(), Risque(dernier=80, vol=0.30, mm50=100, mm200=90, recul_52s=-0.2), cfg)
    assert l3.levier == 1 and "moyennes" in l3.motif_levier
    l4 = lc(4, 90, "crypto", vol=0.20)
    allocation.appliquer_levier(l4, elig(), haussier, cfg)
    assert l4.levier == 1
    l5 = lc(5, 90, vol=0.20)
    allocation.appliquer_levier(l5, elig(leviers=(1,)), haussier, cfg)
    assert l5.levier == 1 and "eToro" in l5.motif_levier
    l6 = lc(6, 90, vol=0.30)  # 2 × 30 % > 50 % de vol cible
    allocation.appliquer_levier(l6, elig(), Risque(dernier=110, vol=0.30, mm50=100, mm200=90, recul_52s=-0.05), cfg)
    assert l6.levier == 1


def test_stop_borne_par_etoro():
    cfg = Allocation()
    l = lc(1, 90, vol=0.20, cours=100)
    l.levier = 2
    allocation.poser_stop(l, elig(), cfg)
    assert l.stop_pct == pytest.approx(max(cfg.stop_min, cfg.stop_sigma * 0.20 / 52 ** 0.5))
    assert l.stop == pytest.approx(100 * (1 - l.stop_pct))
    assert l.stop_pct * l.levier * 100 >= 5.0
    sans = lc(2, 90)
    allocation.poser_stop(sans, elig(), cfg)
    assert sans.stop is None


def note_ticker(iid, score, rang, sens_court=False):
    t = tickers.NoteTicker(iid, nb_detenteurs=5, score=score, rang=rang, consensus_long=0.01)
    if sens_court:
        t.consensus_court = 0.02
    return t


def test_construire_hysteresis_levier_plafond():
    cfg = Allocation(nb_lignes=3, score_min=60, exposition_brute_max=1.5, reserve_cash=0.0, poids_min=0.05, poids_max=0.5)
    notes = [note_ticker(1, 95, 1), note_ticker(2, 90, 2), note_ticker(3, 85, 3, sens_court=True),
             note_ticker(4, 80, 4), note_ticker(5, 55, 5)]
    instruments = {i: {"symbol": f"T{i}", "type": "Stocks"} for i in range(1, 6)}
    risques = {i: Risque(dernier=110, vol=0.15, mm50=100, mm200=90, recul_52s=-0.02) for i in range(1, 6)}
    eligs = {i: elig() for i in range(1, 6)}
    cible = allocation.construire(notes, instruments, eligs, risques, {5: 0.2}, cfg)
    par = {l.instrument_id: l for l in cible.lignes}
    assert set(par) == {1, 2, 5}  # 3 (vendeur) écarté ; 5 détenu, rang 5 ≤ ⌈1,5 × 3⌉ et score 55 ≥ 50 : gardé
    assert ("T3", "consensus vendeur") in cible.ecartes
    assert sum(l.poids for l in cible.lignes) == pytest.approx(1.0)
    # x2 partout aurait donné 185 % d'exposition : on retire le levier du moins bien noté d'abord
    assert par[1].levier == 2 and par[2].levier == 1 and "plafond" in par[2].motif_levier
    assert par[5].levier == 1  # score 55 < 80
    assert cible.exposition_brute <= 1.5 + 1e-9
    assert par[1].stop is not None and par[2].stop is None


def test_construire_remplace_si_hors_hysteresis():
    cfg = Allocation(nb_lignes=2, score_min=60, reserve_cash=0.0)
    notes = [note_ticker(1, 95, 1), note_ticker(2, 90, 2), note_ticker(3, 85, 3), note_ticker(4, 50, 4)]
    instruments = {i: {"symbol": f"T{i}", "type": "Stocks"} for i in range(1, 5)}
    cible = allocation.construire(notes, instruments, {}, {}, {3: 0.5, 4: 0.5}, cfg)
    assert {l.instrument_id for l in cible.lignes} == {3, 1}  # 3 reste (rang 3 ≤ 3) ; 4 sort (rang 4 > 3)
    assert all(l.levier == 1 for l in cible.lignes)  # éligibilité inconnue : pas de levier


# -- Rééquilibrage -----------------------------------------------------------------------------------
def test_ordres_de_revue():
    etat = {"lignes": {"1": {"symbol": "A", "poids": 0.10, "levier": 1}, "2": {"symbol": "B", "poids": 0.10, "levier": 1},
                       "3": {"symbol": "C", "poids": 0.10, "levier": 1}, "4": {"symbol": "D", "poids": 0.10, "levier": 1}}}
    cible = allocation.PortefeuilleCible(lignes=[
        LigneCible(1, "A", "", "stocks", 90, 1, poids=0.105), LigneCible(2, "B", "", "stocks", 90, 2, poids=0.15),
        LigneCible(3, "C", "", "stocks", 90, 3, poids=0.10, levier=2), LigneCible(5, "E", "", "stocks", 90, 4, poids=0.1)])
    o = {x.symbol: x for x in reequilibrage.ordres(etat, cible, 10000, 0.01)}
    assert o["A"].action == "CONSERVER" and o["A"].montant == 0
    assert o["B"].action == "RENFORCER" and o["B"].montant == pytest.approx(500)
    assert o["C"].action == "CHANGER LEVIER" and o["C"].exposition_apres == pytest.approx(2000)
    assert o["D"].action == "VENTE" and o["D"].montant == pytest.approx(-1000)
    assert o["E"].action == "ACHAT"
    assert reequilibrage.ordres(etat, cible, 10000, 0.01)[0].action == "VENTE"


# -- Calendrier ---------------------------------------------------------------------------------------
def test_calendrier_nyse():
    f = calendrier.feries(2026)
    assert dt.date(2026, 4, 3) in f  # Vendredi saint
    assert dt.date(2026, 7, 3) in f  # 4 juillet un samedi
    assert dt.date(2026, 11, 26) in f and dt.date(2026, 9, 7) in f
    assert calendrier.premiere_seance_semaine(dt.date(2026, 9, 10)) == dt.date(2026, 9, 8)  # Labor Day
    assert calendrier.est_jour_de_revue(dt.date(2026, 10, 5))
    ny = calendrier.NY
    assert calendrier.prochaine_revue(dt.datetime(2026, 10, 2, 12, 0, tzinfo=ny)) == \
        dt.datetime(2026, 10, 5, 9, 30, tzinfo=ny)
    assert calendrier.prochaine_revue(dt.datetime(2026, 9, 7, 8, 0, tzinfo=ny)).date() == dt.date(2026, 9, 8)
    assert calendrier.prochaine_revue(dt.datetime(2026, 10, 5, 9, 31, tzinfo=ny)).date() == dt.date(2026, 10, 12)


# -- Client et collecte ----------------------------------------------------------------------------------
def test_lecture_reponse_mcp():
    corps = json.dumps({"statusCode": 200, "isSuccess": True, "body": "{\"a\":1}"})
    brut = "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
        "content": [{"type": "text", "text": corps}]}}) + "\n\n"
    assert lire_reponse_mcp(brut) == (200, "{\"a\":1}", None)
    tronque = json.dumps({"statusCode": 200, "body": "{", "bodyTruncated": True})
    assert lire_reponse_mcp(json.dumps({"result": {"content": [{"text": tronque}]}}))[0] == 413


def test_limiteur_attend_la_fenetre():
    t = [0.0]
    pauses = []
    lim = Limiteur({"defaut": 2}, marge=1.0, horloge=lambda: t[0], sommeil=lambda s: (pauses.append(s), t.__setitem__(0, t[0] + s)))
    for _ in range(3):
        lim.attendre("defaut")
    assert len(pauses) == 1 and pauses[0] == pytest.approx(60.05)


def test_client_reessaie_sur_429(monkeypatch):
    c = ClientEtoro(Connexion(x_user_key="u", x_api_key="a"), limiteur=Limiteur(), sommeil=lambda s: None)
    reponses = [(429, "trop", 1.0), (200, "{\"ok\": true}", None)]
    monkeypatch.setattr(c, "_rest", lambda *a: reponses.pop(0))
    assert c.get("/x") == {"ok": True}
    monkeypatch.setattr(c, "_rest", lambda *a: (403, "interdit", None))
    with pytest.raises(ErreurApi) as e:
        c.get("/x")
    assert e.value.statut == 403
    with pytest.raises(ValueError):
        ClientEtoro(Connexion())


class FauxClient:
    def __init__(self, routes):
        self.routes, self.appels = routes, []

    def get(self, chemin, query=None, pool="defaut"):
        self.appels.append((chemin, dict(query or {})))
        rep = self.routes(chemin, query or {})
        if isinstance(rep, ErreurApi):
            raise rep
        return rep

    def post_lecture(self, chemin, corps, pool="defaut"):
        self.appels.append((chemin, corps))
        return {"eligibilities": [{"instrumentId": i, **elig()} for i in corps["instrumentIds"]]}


def test_collecteur_pagination_cache_et_erreurs(tmp_path):
    def routes(chemin, q):
        if chemin.endswith("/rankings"):
            page = int(q["page"])
            res = [{"username": "A"}, {"username": "B"}] if page == 1 else [{"username": "b"}, {"username": "C"}]
            return {"results": res, "pagination": {"hasNext": page == 1}}
        if "/portfolio/live" in chemin:
            return ErreurApi(404, "inconnu")
        if chemin == "/api/v2/market-data/instruments":
            return {"results": [{"instrumentId": 1, "symbol": "AAA", "displayName": "Aaa ", "type": "Stocks"}],
                    "pagination": {"hasNext": False, "nextPageToken": "MA=="}}
        raise AssertionError(chemin)
    fc = FauxClient(routes)
    col = Collecteur(Snapshot(tmp_path), fc, JOUR)
    assert [l["username"] for l in col.classement("OneYearAgo")] == ["A", "B", "C"]
    assert col.portefeuille_live("X") is None and col.portefeuille_live("X") is None
    assert col.instruments([1]) == {1: {"symbol": "AAA", "nom": "Aaa", "type": "Stocks", "exchangeId": None}}
    n = len(fc.appels)
    hors_ligne = Collecteur(Snapshot(tmp_path), None, JOUR)
    assert len(hors_ligne.classement("OneYearAgo")) == 3 and hors_ligne.instruments([1, 2]).keys() == {1}
    assert hors_ligne.gains("Z") == []
    assert len(fc.appels) == n


# -- Run complet hors ligne ---------------------------------------------------------------------------------
def test_run_complet_hors_ligne(tmp_path):
    from desk_etoro.__main__ import lancer
    snap = Snapshot(tmp_path / "snap")
    noms = [f"pi{i}" for i in range(8)]
    snap.ecrire("classements/OneYearAgo", [ligne_classement(n, gain=0.05 * (i + 1), copiers=10 * (i + 1))
                                           for i, n in enumerate(noms)])
    for i, n in enumerate(noms):
        snap.ecrire(f"live/{n}", live([pos(100, 30), pos(200, 20), pos(300 + i, 10), pos(400, 10, lev=2)]))
        snap.ecrire(f"gains/{n}", {"gains": [{"date": f"2025-{m:02d}-01", "gain": 0.01 * ((m + i) % 3 - 0.5)}
                                             for m in range(1, 13)]})
    snap.ecrire("instruments", {str(k): {"symbol": s, "nom": s, "type": t} for k, s, t in
                                [(100, "AAA", "Stocks"), (200, "BBB", "ETF"), (400, "BTC", "Crypto")]})
    snap.ecrire("eligibilite", {"100": elig(), "200": elig(), "400": elig()})
    clotures = [[(dt.date(2025, 1, 1) + dt.timedelta(days=k)).isoformat(), 100 + k * 0.1 + (k % 5) * 0.2]
                for k in range(300)]
    for iid in (100, 200, 400):
        snap.ecrire(f"cours/{iid}", {"instrumentId": iid, "closes": clotures})
    cfg = Config()
    cfg.dossier_donnees = tmp_path / "donnees"
    cfg.allocation.score_min = 0
    cfg.qualite.quantile_min = 0
    sortie = lancer(cfg, JOUR, snapshot=tmp_path / "snap", hors_ligne=True)
    plan = json.loads((sortie / "plan.json").read_text())
    assert plan["univers"]["votants"] == 8
    assert {l["symbol"] for l in plan["cible"]["lignes"]} == {"AAA", "BBB", "BTC"}
    assert sum(l["poids"] for l in plan["cible"]["lignes"]) + plan["cible"]["cash"] == pytest.approx(1.0, abs=1e-3)
    assert all(o["action"] == "ACHAT" for o in plan["ordres"])
    assert "Portefeuille cible" in (sortie / "rapport.md").read_text()
    etat = json.loads((cfg.dossier_donnees / "etat.json").read_text())
    assert etat["date"] == JOUR.isoformat() and len(etat["lignes"]) == 3
    # Relance le même jour : les ordres repartent de l'état précédent (vide), pas de la cible du matin
    sortie = lancer(cfg, JOUR, snapshot=tmp_path / "snap", hors_ligne=True)
    assert all(o["action"] == "ACHAT" for o in json.loads((sortie / "plan.json").read_text())["ordres"])
