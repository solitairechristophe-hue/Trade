"""Analyse du backtest croisé du Desk Flow (données reconstituées à date par les fichiers reports/backtest/*.csv).

Chaque ligne = un signal (date, titre, sens ±1) et son issue à 7 séances (move_atr, win_1atr…).
Pour chaque facteur, on calcule sa valeur « dans le sens du signal » (> 0 = le facteur confirme),
puis le taux de gain quand il confirme / contredit. Ensuite :
  1. le score du desk tel quel (scanner.scoring.noter) ;
  2. un score « appris » sur les premières dates (facteurs qui aidaient) et testé sur les suivantes.
Usage : python -m scanner.backtest  → reports/backtest/synthese.md
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

from .calibrate import wilson
from .model import FlowAlert, Regime, ScreenerHit, TickerContext
from .scoring import Candidate, noter

D = Path(__file__).resolve().parents[1] / "reports" / "backtest"


def _lire(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(x) -> float | None:
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def charger() -> list[dict]:
    flux = _lire(D.parent / "calibration-signaux.csv")
    for r in flux:
        r["source"] = "flux"
    scr = _lire(D / "panel_screener.csv")
    vus = {(r["date"], r["ticker"]) for r in flux}
    panel = flux + [r for r in scr if (r["date"], r["ticker"]) not in vus]
    scr_idx = {(r["date"], r["ticker"]): r for r in scr}
    feats = {}
    for nom in ("regime", "gex", "gex_screener", "prix_vol", "positionnement"):
        for r in _lire(D / f"{nom}.csv"):
            feats.setdefault((r["date"], r["ticker"]), {}).update({k: v for k, v in r.items() if k not in ("date", "ticker")})
    # variables de marché (par date) réutilisables pour tous les titres de la séance
    par_date: dict[str, dict] = {}
    for r in _lire(D / "regime.csv"):
        par_date.setdefault(r["date"], {k: r[k] for k in ("tide_pente", "tide_niveau", "tide_bias", "spy_tide",
                                                         "qqq_tide", "spy_gex_net", "spy_gex_positive",
                                                         "macro_event_next_day") if k in r})
    out = []
    for r in panel:
        k = (r["date"], r["ticker"])
        row = dict(r)
        row.update(par_date.get(r["date"], {}))
        row.update(feats.get(k, {}))
        s = scr_idx.get(k)
        row["screener_dir"] = s["direction"] if s else ""
        out.append(row)
    return out


def facteurs(r: dict) -> dict[str, float | None]:
    """Valeur de chaque facteur dans le sens du signal (−1..+1 environ ; None = inconnu)."""
    d = int(float(r["direction"]))
    g = lambda k: _f(r.get(k))
    close, atr = g("close_t"), g("atr14")
    f: dict[str, float | None] = {}
    f["flux"] = (1.0 if r.get("source") == "flux" else None)
    sd = r.get("screener_dir")
    f["screener"] = (1.0 if int(float(sd)) == d else -1.0) if sd not in ("", None) else None
    f["regime_marche"] = g("tide_bias") * d if g("tide_bias") is not None else None
    f["regime_secteur"] = g("sector_bias") * d if g("sector_bias") is not None else None
    f["spy_gamma_positif"] = (1.0 if g("spy_gex_positive") == 1 else -1.0) if g("spy_gex_positive") is not None else None
    if close and g("sma20") and g("sma50"):
        f["tendance"] = (0.5 if close > g("sma20") else -0.5) * d + (0.5 if close > g("sma50") else -0.5) * d
    else:
        f["tendance"] = None
    f["momentum_5j"] = math.tanh(g("ret5") / 0.05) * d if g("ret5") is not None else None
    f["rsi_extreme"] = ((50 - g("rsi14")) / 50) * d if g("rsi14") is not None else None  # >0 = survendu pour un achat
    ncp, npp = g("net_call_premium"), g("net_put_premium")
    f["prime_nette_jour"] = math.tanh(((ncp or 0) - (npp or 0)) / 3e6) * d if ncp is not None or npp is not None else None
    f["liquidite_os"] = math.tanh((g("os_ratio") - 0.15) / 0.15) if g("os_ratio") is not None else None
    mc = g("marketcap")
    f["mega_cap"] = (-1.0 if mc and mc >= 500e9 else 0.0) if mc is not None else None
    f["etf"] = (-1.0 if str(r.get("is_etf", "")).lower() in ("1", "true") else 0.0) if r.get("is_etf") not in (None, "") else None
    f["iv_rank_bas"] = (0.5 - g("iv_rank") / (100 if g("iv_rank") > 1 else 1)) if g("iv_rank") is not None else None
    if g("gex_net") is not None:
        f["gamma_negatif"] = 1.0 if g("gex_net") < 0 else -1.0
    else:
        f["gamma_negatif"] = None
    if g("dist_call_wall_atr") is not None and g("dist_put_wall_atr") is not None:
        # hausse : place jusqu'au call wall et support proche ; baisse : l'inverse
        cap = lambda x: max(-5.0, min(5.0, x))  # murs très éloignés : distance plafonnée à 5 ATR
        place, appui = (cap(g("dist_call_wall_atr")), cap(g("dist_put_wall_atr"))) if d > 0 else \
            (cap(g("dist_put_wall_atr")), cap(g("dist_call_wall_atr")))
        f["murs_gamma"] = max(-1.0, min(1.0, math.tanh(place) - 0.5 * math.tanh(appui)))
    else:
        f["murs_gamma"] = None
    mp = g("max_pain_nearest")
    f["attraction_max_pain"] = (math.tanh((mp - close) / atr) * d) if mp and close and atr else None
    f["au_dessus_flip"] = ((1.0 if g("above_flip") == 1 else -1.0) * d) if g("above_flip") is not None else None
    oc, op = g("oi_call_prem_d"), g("oi_put_prem_d")
    f["open_interest"] = math.tanh(((oc or 0) - (op or 0)) / 2e6) * d if oc is not None or op is not None else None
    f["dark_pool"] = min(1.0, g("dp_vs_adv") / 0.10) if g("dp_vs_adv") is not None else None
    ib, isell = g("insider_buy_30d"), g("insider_sell_30d")
    f["inities"] = math.tanh(((ib or 0) - 0.5 * (isell or 0)) / 2e6) * d if ib is not None or isell is not None else None
    cb, cs = g("congress_buys_60d"), g("congress_sells_60d")
    f["congres"] = max(-1.0, min(1.0, ((cb or 0) - (cs or 0)) / 3)) * d if cb is not None or cs is not None else None
    au, ad = g("analyst_up_30d"), g("analyst_down_30d")
    f["analystes"] = max(-1.0, min(1.0, ((au or 0) - (ad or 0)) / 3)) * d if au is not None or ad is not None else None
    f["short_volume"] = (g("short_vol_ratio_5d") - 0.45) * 4 * d if g("short_vol_ratio_5d") is not None else None
    f["resultats_7j"] = (-1.0 if g("earnings_within_7") == 1 else 0.0) if g("earnings_within_7") is not None else None
    f["saisonnalite"] = math.tanh(g("season_avg_month") / (5 if abs(g("season_avg_month")) > 1 else 0.05)) * d if g("season_avg_month") is not None else None
    f["macro_lendemain"] = (-1.0 if g("macro_event_next_day") == 1 else 0.0) if g("macro_event_next_day") is not None else None
    return f


def _taux(rows: list[dict], cle: str = "win_1atr") -> tuple[int, int, float]:
    n = len(rows)
    w = sum(1 for r in rows if _f(r.get(cle)) == 1)
    return n, w, (w / n if n else float("nan"))


def univarie(rows: list[dict]) -> list[dict]:
    noms = sorted({k for r in rows for k in r["_f"]})
    res = []
    for k in noms:
        pos = [r for r in rows if (r["_f"].get(k) or 0) > 0.05]
        neg = [r for r in rows if r["_f"].get(k) is not None and r["_f"][k] < -0.05]
        cov = sum(1 for r in rows if r["_f"].get(k) is not None)
        np_, wp, tp = _taux(pos)
        nn, wn, tn = _taux(neg)
        mp = sum(_f(r["move_atr"]) for r in pos) / np_ if np_ else float("nan")
        mn = sum(_f(r["move_atr"]) for r in neg) / nn if nn else float("nan")
        res.append({"facteur": k, "couverture": cov, "n_conf": np_, "gain_conf": tp, "ic_conf": wilson(wp, np_),
                    "mvt_conf": mp, "n_contra": nn, "gain_contra": tn, "mvt_contra": mn,
                    "ecart": (tp - tn) if np_ and nn else float("nan")})
    return res


def score_desk(r: dict) -> float:
    """Score du desk (scanner.scoring) reconstruit avec les colonnes disponibles."""
    g = lambda k: _f(r.get(k))
    d = int(float(r["direction"]))
    tk, jour = r["ticker"], dt.date.fromisoformat(r["date"])
    c = Candidate(ticker=tk)
    prem = g("net_premium")
    if r.get("source") == "flux" and prem:
        c.alerts.append(FlowAlert(ticker=tk, type="call" if d > 0 else "put", premium=prem, size=0, volume=0,
                                  open_interest=0, ask_side_premium=prem, bid_side_premium=0, strike=0,
                                  expiry=jour + dt.timedelta(days=30), underlying_price=g("close_t") or 0, rule=""))
    if r.get("screener_dir") not in ("", None):
        c.screener.append(ScreenerHit(tk, "screener", int(float(r["screener_dir"])) > 0))
    ctx = TickerContext(ticker=tk, price=g("close_t") or 0, atr14=g("atr14") or 0, sma20=g("sma20") or 0,
                        sma50=g("sma50") or 0, sector=r.get("sector") or "", marketcap=g("marketcap") or 0,
                        call_wall=g("call_wall"), put_wall=g("put_wall"), gex_net=g("gex_net"),
                        net_call_premium=g("net_call_premium") or 0, net_put_premium=g("net_put_premium") or 0,
                        options_volume=(g("call_volume") or 0) + (g("put_volume") or 0), stock_volume=g("stock_volume") or 0,
                        oi_change_call_prem=g("oi_call_prem_d") or 0, oi_change_put_prem=g("oi_put_prem_d") or 0,
                        insider_buy_value_30d=g("insider_buy_30d") or 0, insider_sell_value_30d=g("insider_sell_30d") or 0,
                        congress_buys_60d=int(g("congress_buys_60d") or 0), congress_sells_60d=int(g("congress_sells_60d") or 0),
                        analyst_upgrades=int(g("analyst_up_30d") or 0), analyst_downgrades=int(g("analyst_down_30d") or 0))
    if g("days_to_earnings") is not None:
        ctx.next_earnings = jour + dt.timedelta(days=int(g("days_to_earnings") * 7 / 5))
    if g("season_avg_month") is not None:
        s = g("season_avg_month")
        ctx.seasonality_month_avg = s / 100 if abs(s) > 1 else s
    c.context = ctx
    reg = Regime(bias=g("tide_bias") or 0.0)
    if r.get("sector") and g("sector_bias") is not None:
        reg.sector_bias[r["sector"]] = g("sector_bias")
    noter(c, reg, jour, 50)
    if not c.direction:
        return 0.0
    return c.score if (1 if c.direction == "up" else -1) == d else 100 - c.score  # score dans le sens du signal


def _bs(S: float, K: float, T: float, iv: float, call: bool) -> float:
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    return S * N(d1) - K * N(d2) if call else K * N(-d2) - S * N(-d1)


def pnl_spread(r: dict, dte: int = 35, tenue_j: int = 10, largeur_atr: float = 1.5,
               cout_frac: float = 0.05) -> float | None:
    """Rendement simulé d'un vertical acheté (prime = 1) : longue à la monnaie, courte à 1,5 ATR dans le sens
    du signal, échéance 35 jours, sortie après 7 séances (10 jours). Prix Black-Scholes à l'IV 30 j du jour
    d'entrée, inchangée à la sortie ; coût d'exécution = 5 % de la largeur à l'aller et au retour."""
    S0, S1, atr, iv = _f(r.get("close_t")), _f(r.get("close_t7")), _f(r.get("atr14")), _f(r.get("iv30d"))
    if not (S0 and S1 and atr and iv) or iv > 2.5:
        return None
    d = int(float(r["direction"]))
    call = d > 0
    K1, K2 = S0, S0 + d * largeur_atr * atr
    w = abs(K2 - K1)
    v = lambda S, T: _bs(S, K1, T, iv, call) - _bs(S, K2, T, iv, call)
    entree = v(S0, dte / 365) + cout_frac * w
    sortie = max(0.0, v(S1, (dte - tenue_j) / 365) - cout_frac * w)
    return (sortie - entree) / entree if entree > 0 else None


def bloc_pnl(titre: str, groupes: list[tuple[str, list[dict]]]) -> list[str]:
    L = ["", f"## {titre}", "", "Rendement simulé d'un spread acheté, en multiple de la prime payée.", "",
         "| Groupe | n | rendement moyen | médiane | trades gagnants |", "|---|---|---|---|---|"]
    for nom, sel in groupes:
        x = sorted(v for v in (pnl_spread(r) for r in sel) if v is not None)
        if not x:
            L.append(f"| {nom} | 0 | – | – | – |")
            continue
        L.append(f"| {nom} | {len(x)} | {sum(x) / len(x):+.1%} | {x[len(x) // 2]:+.1%} | {sum(1 for v in x if v > 0) / len(x):.0%} |")
    return L


def par_tranche(rows: list[dict], cle: str, bornes: list[float]) -> list[tuple[str, int, float, tuple, float]]:
    out = []
    for lo, hi in zip(bornes, bornes[1:]):
        sel = [r for r in rows if lo <= r[cle] < hi]
        n, w, t = _taux(sel)
        mv = sum(_f(r["move_atr"]) for r in sel) / n if n else float("nan")
        out.append((f"{lo:g}–{hi:g}", n, t, wilson(w, n), mv))
    return out


def hasard(rows: list[dict], seuil: float = 1.0) -> float:
    m = [abs(_f(r["move_atr"])) for r in rows if _f(r.get("move_atr")) is not None]
    return 0.5 * sum(1 for x in m if x >= seuil) / len(m) if m else float("nan")


CONCLUSION = """## Conclusions (2 octobre 2026)

- **Aucune source seule ne bat le hasard** sur 830 signaux : flux d'options, screeners, prime nette du jour,
  tendance, momentum, régime de marché, initiés, analystes, dark pool. Le score d'origine du desk n'était pas
  monotone : ses notes au-dessus de 75 faisaient le moins bien.
- **Les murs gamma sont le seul facteur robuste.** Quand le trade bute sur un mur, l'action ne fait 1 ATR dans le
  bon sens que 9 à 15 % du temps, sur chaque moitié de la période et sur chaque panel. Ces trades sont rejetés.
- **Setup gamma** (murs favorables et gamma des dealers négatif) : 33 % de réussite à 1 ATR contre 26 % au hasard,
  repéré sur le panel flux et confirmé sur le panel screener (32,6 %, n = 46). Sur 84 trades, un spread simulé
  gagne +2,9 % de la prime en moyenne si l'exécution coûte 1,5 % de la largeur par sens, avec une erreur type de
  4,8 % : **prometteur, pas prouvé**. À 5 % de coût par sens, il perd 10 à 15 %.
- **L'exécution décide de tout** : entrée au mid, spreads dont l'écart achat-vente cumulé reste sous 3 % de la
  largeur, aucune poursuite du prix.
- Limites : deux mois d'un marché plat, signaux corrélés au sein d'une séance, prix d'options simulés
  (Black-Scholes à l'IV du jour), variations d'open interest non testables à date, saisonnalité biaisée,
  certains cours et données d'initiés obtenus hors Unusual Whales pour le seul besoin du backtest."""


def analyse() -> str:
    rows = [r for r in charger() if _f(r.get("move_atr")) is not None]
    for r in rows:
        r["_f"] = facteurs(r)
        r["_score"] = score_desk(r)
    dates = sorted({r["date"] for r in rows})
    coupe = dates[len(dates) // 2]
    train = [r for r in rows if r["date"] < coupe]
    test = [r for r in rows if r["date"] >= coupe]
    L = ["# Backtest croisé du Desk Flow", "", CONCLUSION, "", "## Détail", "",
         f"{len(rows)} signaux ({sum(1 for r in rows if r.get('source') == 'flux')} flux, "
         f"{sum(1 for r in rows if r.get('source') != 'flux')} screener seul), {len(dates)} séances "
         f"({dates[0]} → {dates[-1]}), issue à 7 séances. Hasard au seuil 1 ATR : {hasard(rows):.3f}.", ""]
    L += ["## Facteurs un par un (gain = mouvement ≥ 1 ATR dans le sens du signal)", "",
          "| Facteur | Couverture | n confirme | gain | IC 95 % | mvt moyen (ATR) | n contredit | gain | mvt moyen | écart |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    uni = univarie(rows)
    for u in sorted(uni, key=lambda u: -(u["ecart"] if u["ecart"] == u["ecart"] else -9)):
        L.append(f"| {u['facteur']} | {u['couverture']} | {u['n_conf']} | {u['gain_conf']:.3f} | {u['ic_conf'][0]:.2f}–{u['ic_conf'][1]:.2f} | "
                 f"{u['mvt_conf']:+.2f} | {u['n_contra']} | {u['gain_contra']:.3f} | {u['mvt_contra']:+.2f} | {u['ecart']:+.3f} |")
    L += ["", "## Score du desk actuel (dans le sens du signal)", "",
          "| Score | n | gain 1 ATR | IC 95 % | mvt moyen |", "|---|---|---|---|---|"]
    for t, n, g, ic, mv in par_tranche(rows, "_score", [0, 45, 55, 65, 75, 101]):
        L.append(f"| {t} | {n} | {g:.3f} | {ic[0]:.2f}–{ic[1]:.2f} | {mv:+.2f} |")
    # score appris : facteurs dont l'écart était > 0,05 avec n ≥ 10 de chaque côté sur la première moitié
    appris = [u["facteur"] for u in univarie(train) if u["ecart"] == u["ecart"] and u["ecart"] > 0.05
              and u["n_conf"] >= 10 and u["n_contra"] >= 10]
    for r in rows:
        r["_appris"] = sum(1 for k in appris if (r["_f"].get(k) or 0) > 0.05) - \
                       sum(1 for k in appris if (r["_f"].get(k) or 0) < -0.05)
    L += ["", f"## Score appris (dates < {coupe}) puis testé (dates ≥ {coupe})", "",
          "Facteurs retenus sur la première moitié : " + (", ".join(appris) or "aucun") + ".", "",
          "| Échantillon | Votes nets | n | gain 1 ATR | IC 95 % | mvt moyen |", "|---|---|---|---|---|---|"]
    for nom, ech in (("apprentissage", train), ("test", test)):
        for lo, hi in ((-99, 0), (0, 1), (1, 2), (2, 99)):
            sel = [r for r in ech if lo <= r["_appris"] < hi]
            n, w, g = _taux(sel)
            mv = sum(_f(r["move_atr"]) for r in sel) / n if n else float("nan")
            L.append(f"| {nom} | {'≥' + str(lo) if hi == 99 else (str(lo) if hi - lo == 1 else '< 0')} | {n} | "
                     f"{g:.3f} | {wilson(w, n)[0]:.2f}–{wilson(w, n)[1]:.2f} | {mv:+.2f} |")
    # Validation dédiée aux facteurs gamma : repérés sur le panel flux, testés sur les signaux screener
    L += ["", "## Filtre gamma : repéré sur le panel flux, testé sur le panel screener", "",
          "Règle : murs gamma favorables (> 0) ET gamma des dealers négatif.", "",
          "| Panel | Règle | n | gain 1 ATR | IC 95 % | mvt moyen |", "|---|---|---|---|---|---|"]
    for nom, ech in (("flux (découverte)", [r for r in rows if r.get("source") == "flux"]),
                     ("screener (test)", [r for r in rows if r.get("source") != "flux"])):
        avec = [r for r in ech if r["_f"].get("murs_gamma") is not None and r["_f"].get("gamma_negatif") is not None]
        for regle, sel in (("vérifiée", [r for r in avec if r["_f"]["murs_gamma"] > 0 and r["_f"]["gamma_negatif"] > 0]),
                           ("murs seuls > 0", [r for r in avec if r["_f"]["murs_gamma"] > 0]),
                           ("non vérifiée", [r for r in avec if not (r["_f"]["murs_gamma"] > 0 and r["_f"]["gamma_negatif"] > 0)]),
                           ("tous", avec)):
            n, w, g = _taux(sel)
            mv = sum(_f(r["move_atr"]) for r in sel) / n if n else float("nan")
            L.append(f"| {nom} | {regle} | {n} | {g:.3f} | {wilson(w, n)[0]:.2f}–{wilson(w, n)[1]:.2f} | {mv:+.2f} |")
    gam = lambda r: r["_f"].get("murs_gamma") is not None and r["_f"]["murs_gamma"] > 0 and (r["_f"].get("gamma_negatif") or 0) > 0
    contre = lambda r: r["_f"].get("murs_gamma") is not None and r["_f"]["murs_gamma"] < -0.05
    flux_rows = [r for r in rows if r.get("source") == "flux"]
    scr_rows = [r for r in rows if r.get("source") != "flux"]
    L += bloc_pnl("Spreads simulés", [
        ("tous les signaux", rows),
        ("flux seul", flux_rows),
        ("screener seul", scr_rows),
        ("règle gamma vérifiée, panel flux", [r for r in flux_rows if gam(r)]),
        ("règle gamma vérifiée, panel screener (test)", [r for r in scr_rows if gam(r)]),
        ("murs gamma contre le trade", [r for r in rows if contre(r)]),
        ("score du desk ≥ 65", [r for r in rows if r["_score"] >= 65]),
        ("score appris ≥ 2, dates de test", [r for r in test if r["_appris"] >= 2]),
    ])
    L += ["", "Lecture : un facteur utile a un « gain » nettement plus haut quand il confirme que quand il contredit, "
          "et un mouvement moyen positif quand il confirme. Avec moins de 300 signaux sur deux mois, un écart de "
          "moins de 10 points n'est pas distinguable du bruit."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    t = analyse()
    (D / "synthese.md").write_text(t, encoding="utf-8")
    print(t)
