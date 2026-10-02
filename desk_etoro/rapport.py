"""Sorties d'un run : plan.json (lisible par une machine) et rapport.md (lecture humaine)."""
from __future__ import annotations

from dataclasses import asdict

from .config import Config
from .desk import Resultat
from .qualite import CRITERES, FAMILLES
from .reequilibrage import en_dicts

NOMS_FAMILLES = {"performance": "Performance", "ajuste_risque": "Ajusté du risque", "risque": "Maîtrise du risque",
                 "regularite": "Régularité", "confiance": "Confiance"}


def _pct(x, n=1):
    return "—" if x is None else f"{x * 100:.{n}f} %"


def _num(x, n=2):
    return "—" if x is None else f"{x:.{n}f}"


def _arrondi(d: dict, n: int = 4) -> dict:
    return {k: (round(v, n) if isinstance(v, float) else v) for k, v in d.items()}


def plan(res: Resultat, cfg: Config) -> dict:
    sym = lambda i: (res.instruments.get(i) or {}).get("symbol") or str(i)  # noqa: E731
    return {
        "desk": "etoro-consensus-pi",
        "date": res.date,
        "prochaine_revue": res.prochaine_revue,
        "univers": res.univers,
        "cible": {
            "cash": round(res.cible.cash, 4),
            "exposition_brute": round(res.cible.exposition_brute, 4),
            "lignes": [_arrondi(asdict(l)) for l in res.cible.lignes],
            "ecartes": [{"symbol": s, "motif": m} for s, m in res.cible.ecartes],
        },
        "ordres": en_dicts(res.ordres),
        "tickers": [{
            "rang": t.rang, "instrument_id": t.instrument_id, "symbol": sym(t.instrument_id),
            "nom": (res.instruments.get(t.instrument_id) or {}).get("nom", ""),
            "classe": (res.instruments.get(t.instrument_id) or {}).get("type", ""),
            "score": round(t.score, 2), "sens": t.sens, "nb_detenteurs": t.nb_detenteurs,
            "consensus": round(t.consensus, 5), "largeur": round(t.largeur, 4), "conviction": round(t.conviction, 4),
            "qualite_detenteurs": round(t.qualite_detenteurs, 4),
            "fraicheur": None if t.fraicheur is None else round(t.fraicheur, 4),
            "part_levier_detenteurs": round(t.part_levier_detenteurs, 4),
            "pnl_latent_moyen_pct": round(t.pnl_latent_moyen, 2),
            "composantes": _arrondi(t.composantes),
            "principaux_detenteurs": [{"username": u, "poids": round(w, 4), "qualite": round(q, 3)}
                                      for u, w, q in t.detenteurs[:5]],
        } for t in res.tickers[:150]],
        "portefeuilles": [{
            "username": n.username, "palier": n.palier, "qualite": round(n.qualite, 4), "vote": round(n.vote, 4),
            "familles": _arrondi(n.familles), "criteres": _arrondi(n.criteres, 6),
            "composition": n.composition.resume() if n.composition else None,
        } for n in res.portefeuilles],
        "config": cfg.en_dict(),
    }


def markdown(res: Resultat, cfg: Config) -> str:
    a = cfg.allocation
    u = res.univers
    sym = lambda i: (res.instruments.get(i) or {}).get("symbol") or str(i)  # noqa: E731
    L = [f"# Desk eToro — consensus des Popular Investors — {res.date}", ""]
    L.append(f"Prochaine revue : **{res.prochaine_revue}** (ouverture de la première séance de la semaine).")
    L.append("")
    L.append(f"Univers : {u['classes']} Popular Investors classés ({u['periode']}), {u['retenus']} retenus après filtres, "
             f"{u['notes']} examinés en détail, **{u['votants']} votants**, {u['tickers_croises']} instruments croisés, "
             f"{u['tickers_notes']} tickers notés (≥ {cfg.tickers.detenteurs_min} détenteurs).")
    if u.get("exclus"):
        L.append("Exclusions : " + ", ".join(f"{m} ({n})" for m, n in u["exclus"].items()) + ".")
    L.append("")

    L += ["## Portefeuille cible", "",
          f"Liquidités {_pct(res.cible.cash)} · exposition brute {_pct(res.cible.exposition_brute)} "
          f"· capital de référence {a.capital:,.0f}".replace(",", " "), "",
          "| # | Ticker | Nom | Classe | Score | Poids | Levier | Exposition | Stop | Vol. | Détenteurs | Motif du levier |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, l in enumerate(res.cible.lignes, 1):
        stop = "—" if l.stop is None else f"{l.stop:g} (−{l.stop_pct * 100:.0f} %)"
        L.append(f"| {i} | **{l.symbol}** | {l.nom} | {l.classe} | {l.score:.0f} | {_pct(l.poids)} | x{l.levier} | "
                 f"{_pct(l.exposition)} | {stop} | {_pct(l.vol, 0)} | {l.nb_detenteurs} | {l.motif_levier} |")
    if res.cible.ecartes:
        L += ["", "Bien notés mais écartés : " + ", ".join(f"{s} ({m})" for s, m in res.cible.ecartes[:15]) + "."]
    L.append("")

    L += ["## Ordres de la revue", "",
          "Proposés, non transmis. Les ventes d'abord, pour libérer la marge.", "",
          "| Action | Ticker | Poids avant → après | Levier | Montant (marge) | Exposition après | Stop |",
          "|---|---|---|---|---|---|---|"]
    for o in res.ordres:
        if o.action == "CONSERVER":
            continue
        L.append(f"| {o.action} | {o.symbol} | {_pct(o.poids_avant)} → {_pct(o.poids_apres)} | "
                 f"x{o.levier_avant} → x{o.levier_apres} | {o.montant:+,.0f} | {o.exposition_apres:,.0f} | "
                 f"{'—' if o.stop is None else f'{o.stop:g}'} |".replace(",", " "))
    conserves = [o.symbol for o in res.ordres if o.action == "CONSERVER"]
    if conserves:
        L += ["", "Conservés sans changement : " + ", ".join(conserves) + "."]
    L.append("")

    L += ["## Tickers les mieux notés", "",
          "| Rang | Ticker | Classe | Score | Détenteurs | Consensus | Largeur | Conviction | Qualité dét. | Fraîcheur | Principaux détenteurs |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in res.tickers[:40]:
        meta = res.instruments.get(t.instrument_id) or {}
        det = ", ".join(u_ for u_, _, _ in t.detenteurs[:3])
        L.append(f"| {t.rang} | **{sym(t.instrument_id)}** | {meta.get('type', '')} | {t.score:.0f} | {t.nb_detenteurs} | "
                 f"{_pct(t.consensus, 2)} | {_pct(t.largeur, 0)} | {_pct(t.conviction, 1)} | {t.qualite_detenteurs:.2f} | "
                 f"{_pct(t.fraicheur, 0)} | {det} |")
    L.append("")

    L += ["## Portefeuilles les mieux notés", "",
          "| # | Investisseur | Palier | Qualité | " + " | ".join(NOMS_FAMILLES[f] for f in FAMILLES) +
          " | Gain 1 an | Sharpe | Drawdown 36 m | Risque | Copieurs | Lignes |",
          "|---|---|---|---|" + "---|" * len(FAMILLES) + "---|---|---|---|---|---|"]
    for i, n in enumerate(res.portefeuilles[:30], 1):
        c = n.criteres
        L.append(f"| {i} | {n.username} | {n.palier} | {n.qualite:.3f} | " +
                 " | ".join(f"{n.familles.get(f, 0):.2f}" for f in FAMILLES) +
                 f" | {_pct(c.get('gain_1a'))} | {_num(c.get('sharpe'))} | {_pct(c.get('drawdown_max'))} | "
                 f"{_num(c.get('risk_score'), 0)} | {int(c.get('copieurs') or 0)} | "
                 f"{len(n.composition.lignes) if n.composition else 0} |")
    L.append("")

    L += ["## Critères de qualité", "",
          "Chaque critère est classé en rang centile dans l'univers, puis moyenné par famille. Poids des familles : " +
          ", ".join(f"{NOMS_FAMILLES[f]} {getattr(cfg.qualite, 'poids_' + f):.0%}" for f in FAMILLES) +
          f". Vote d'un portefeuille = qualité^{cfg.qualite.exposant:g} (le quart le moins bien noté ne vote pas).", "",
          "| Famille | Critère | Source | Sens |", "|---|---|---|---|"]
    for nom, fam, src, haut, lib in CRITERES:
        L.append(f"| {NOMS_FAMILLES[fam]} | {lib} | {src} | {'↑' if haut else '↓'} |")
    L.append("")
    t = cfg.tickers
    L += ["## Méthode", "",
          f"- **Score d'un ticker** (0–100) : somme pondérée du consensus pondéré par la qualité ({t.poids_consensus:.0%}), "
          f"de la largeur de détention ({t.poids_largeur:.0%}), de la conviction des détenteurs ({t.poids_conviction:.0%}), "
          f"de la qualité moyenne des détenteurs ({t.poids_qualite_detenteurs:.0%}) et des entrées de moins de "
          f"{t.jours_fraicheur} jours ({t.poids_fraicheur:.0%}), chacun ramené sur [0, 1] entre son quantile 2 % et "
          f"son maximum (échelle logarithmique pour les trois premiers).",
          f"- **Poids** ∝ ((score − {a.score_plancher_poids:g}) / {100 - a.score_plancher_poids:g})^{a.exposant_score:g} "
          f"/ volatilité^{a.exposant_vol:g}, "
          f"entre {_pct(a.poids_min, 0)} et "
          f"{_pct(a.poids_max, 0)} par ligne, crypto ≤ {_pct(a.poids_max_crypto, 0)}, réserve {_pct(a.reserve_cash, 0)}.",
          f"- **Facteur multiplicateur** : score ≥ {a.score_levier:g} et rang ≤ {a.rang_max_levier}, classe {', '.join(a.classes_levier)}, volatilité ≤ "
          f"{_pct(a.vol_max_levier, 0)}, cours au-dessus des moyennes 50 et 200 jours, à moins de "
          f"{_pct(-a.drawdown_max_levier, 0)} de son plus haut, levier proposé par eToro ; levier = le plus grand permis "
          f"(≤ x{a.levier_max}) tel que levier × vol ≤ {_pct(a.vol_cible_position, 0)} ; exposition brute ≤ "
          f"{_pct(a.exposition_brute_max, 0)}. Stop des lignes à levier : {a.stop_sigma:g} × vol hebdomadaire, "
          f"entre {_pct(a.stop_min, 0)} et {_pct(a.stop_max, 0)}.",
          f"- **Revue** chaque semaine à l'ouverture : une ligne détenue reste tant que son rang ≤ "
          f"{a.hysteresis_rang:g} × {a.nb_lignes} et son score ≥ {a.score_min - a.hysteresis_score:g} ; "
          f"écarts de poids < {_pct(a.bande_reequilibrage, 0)} ignorés.",
          "", "_Aide à la décision, pas un conseil en investissement. Les portefeuilles copiés reflètent des décisions "
          "passées d'autres investisseurs ; le levier amplifie les pertes._", ""]
    return "\n".join(L)
