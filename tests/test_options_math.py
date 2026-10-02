import math

import pytest

from desk_pi_ibkr import options_math as om

S, K, T, R, Q, V = 100.0, 105.0, 0.5, 0.04, 0.01, 0.3


def test_parite_call_put():
    c = om.bs_prix(S, K, T, R, Q, V, "C")
    p = om.bs_prix(S, K, T, R, Q, V, "P")
    assert c - p == pytest.approx(S * math.exp(-Q * T) - K * math.exp(-R * T), abs=1e-10)


@pytest.mark.parametrize("droit", ["C", "P"])
def test_grecques_par_differences_finies(droit):
    g = om.bs_grecques(S, K, T, R, Q, V, droit)
    h = 1e-3
    p = lambda s=S, t=T, v=V, r=R: om.bs_prix(s, K, t, r, Q, v, droit)  # noqa: E731
    assert g.prix == pytest.approx(p())
    assert g.delta == pytest.approx((p(s=S + h) - p(s=S - h)) / (2 * h), rel=1e-5)
    assert g.gamma == pytest.approx((p(s=S + h) - 2 * p() + p(s=S - h)) / h ** 2, rel=1e-3)
    assert g.vega == pytest.approx((p(v=V + h) - p(v=V - h)) / (2 * h) / 100, rel=1e-5)
    assert g.theta == pytest.approx(-(p(t=T + h) - p(t=T - h)) / (2 * h) / 365, rel=1e-4)
    assert g.rho == pytest.approx((p(r=R + h) - p(r=R - h)) / (2 * h) / 100, rel=1e-4)


@pytest.mark.parametrize("droit,k", [("C", 80), ("C", 120), ("P", 95), ("P", 130)])
def test_iv_aller_retour(droit, k):
    prix = om.bs_prix(S, k, T, R, Q, 0.42, droit)
    assert om.iv_implicite(prix, S, k, T, R, Q, droit) == pytest.approx(0.42, abs=1e-6)
    tres_bas = om.iv_implicite(1e-6, S, k, T, R, Q, droit)  # sous la valeur intrinsèque actualisée : None
    assert tres_bas is None or 0 < tres_bas < 5
    assert om.iv_implicite(S * 2, S, k, T, R, Q, droit) is None  # au-delà de toute volatilité


def test_americain():
    eu_put = om.bs_prix(S, K, T, R, 0.0, V, "P")
    am_put = om.prix_americain(S, K, T, R, 0.0, V, "P")
    assert am_put > eu_put  # prime d'exercice anticipé du put
    am_call = om.prix_americain(S, K, T, R, 0.0, V, "C")
    assert am_call == pytest.approx(om.bs_prix(S, K, T, R, 0.0, V, "C"), rel=2e-3)  # sans dividende : européen


def test_scenarios_et_esperance():
    sc = om.cours_scenarios(S, 0.25, 0.10, Q, V)
    assert sum(w for _, w in sc) == pytest.approx(1.0)
    assert sum(x * w for x, w in sc) == pytest.approx(S * math.exp((0.10 - Q) * 0.25), rel=1e-6)
    esp, p, cvar = om.esperance(sc, lambda x: x - S)
    assert esp == pytest.approx(S * (math.exp((0.10 - Q) * 0.25) - 1), rel=1e-4)
    assert 0.5 < p < 0.6 and cvar < -20
    avec_saut = om.cours_scenarios(S, 0.25, 0.10, Q, V, saut=0.08)
    var = lambda s: sum((math.log(x / S)) ** 2 * w for x, w in s)  # noqa: E731
    assert var(avec_saut) > var(sc)


def test_probabilites():
    assert om.proba_finir_au_dela(S, S, T, 0.0, 0.0, V) == pytest.approx(om.ncdf(-0.5 * V * math.sqrt(T)))
    # Sans dérive du log, toucher = 2 × finir au-delà (principe de réflexion)
    mu = 0.5 * V * V
    p_t = om.proba_toucher(S, 120, T, mu, 0.0, V)
    p_f = om.proba_finir_au_dela(S, 120, T, mu, 0.0, V)
    assert p_t == pytest.approx(2 * p_f, rel=1e-9)
    assert om.proba_toucher(S, 80, T, mu, 0.0, V) == pytest.approx(2 * om.proba_finir_au_dela(S, 80, T, mu, 0.0, V, False))
    assert om.proba_toucher(S, S, T, 0.1, 0, V) == 1.0
