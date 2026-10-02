"""Écriture des tickets (format du robot) et du rapport horaire en Markdown."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .model import Regime
from .scoring import Candidate
from .sizing import Dimensionnee


def ticket_id(desk: str, jour: dt.date, symbol: str) -> str:
    return f"{desk}-{jour.isoformat()}-{symbol}"


def vers_ticket(d: Dimensionnee, desk: str, jour: dt.date) -> dict:
    p = d.prop
    t = {
        "id": ticket_id(desk, jour, p.symbol),
        "symbol": p.symbol,
        "direction": p.direction,
        "side": p.side,
        "quantity": d.quantity,
        "limit_price": p.limit_price,
        "price_cap": p.price_cap,
        "take_profit": p.take_profit,
        "stop_loss": p.stop_loss,
        "max_loss": d.max_loss,
        "premium": d.premium,
        "legs": [dict(l) for l in p.legs],
        "condition": p.condition,
        "underlying_stop": p.underlying_stop,
        "time_exit": p.time_exit.isoformat(),
        "valid_until": jour.isoformat(),
        "note": f"{p.note} | score {d.score:.0f} | p {d.p_win:.0%} | EV {d.ev:+.0f} $",
    }
    if t["condition"] is None:
        del t["condition"]
    return t


def ecrire_tickets(dossier: Path, desk: str, jour: dt.date, nouveaux: list[dict]) -> Path:
    """Ajoute les tickets au fichier du jour (un fichier par desk et par jour, ids uniques)."""
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"{jour.isoformat()}-{desk}.json"
    doc = {"run_date": jour.isoformat(), "desk": desk, "tickets": []}
    if f.exists():
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    vus = {t["id"] for t in doc.get("tickets", [])}
    doc["tickets"] = doc.get("tickets", []) + [t for t in nouveaux if t["id"] not in vus]
    f.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return f


def rapport_markdown(quand: dt.datetime, regime: Regime, nav: float, retenus: list[Dimensionnee],
                     etudies: list[tuple[Candidate, str]], feeds: dict[str, str], erreurs: list[str]) -> str:
    """Rapport lisible : régime, opportunités retenues, candidats écartés, couverture des flux."""
    L = [f"# Desk Flow — {quand.strftime('%Y-%m-%d %H:%M')} (New York)", ""]
    L.append(f"NAV IBKR : {nav:,.0f} $. Biais de marché {regime.bias:+.2f}"
             + (" — **RISK OFF**" if regime.risk_off else "") + ".")
    for n in regime.notes:
        L.append(f"- {n}")
    if regime.sector_bias:
        top = sorted(regime.sector_bias.items(), key=lambda kv: kv[1], reverse=True)
        L.append("- Secteurs : " + ", ".join(f"{s} {b:+.2f}" for s, b in top[:4]) + " … "
                 + ", ".join(f"{s} {b:+.2f}" for s, b in top[-2:]))
    L += ["", "## Opportunités retenues (ordres générés pour IBKR)", ""]
    if not retenus:
        L.append("_Aucune opportunité ne passe les filtres cette heure._")
    else:
        L.append("| # | Titre | Sens | Structure | Qté | Limite | Plafond | TP | SL | Prime $ | Risque $ | Score | p | EV $ |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for i, d in enumerate(retenus, 1):
            p = d.prop
            L.append(f"| {i} | **{p.symbol}** | {'↑' if p.direction == 'up' else '↓'} | {p.note.split(' (')[0]} | "
                     f"{d.quantity} | {p.limit_price:.2f} | {p.price_cap:.2f} | {p.take_profit:.2f} | {p.stop_loss:.2f} | "
                     f"{d.premium:.0f} | {d.max_loss:.0f} | {d.score:.0f} | {d.p_win:.0%} | {d.ev:+.0f} |")
        L.append("")
        for d in retenus:
            p = d.prop
            cond = f"si l'action {p.condition['op']} {p.condition['price']}" if p.condition else "sans condition"
            L.append(f"**{p.symbol}** — {p.side} {d.quantity} × {p.note}. Entrée {cond}, "
                     f"stop action {p.underlying_stop}, sortie temps {p.time_exit.isoformat()}.")
    L += ["", "## Candidats étudiés", ""]
    L.append("| Titre | Sens | Score | Sources | Décision | Raisons |")
    L.append("|---|---|---|---|---|---|")
    for c, decision in etudies:
        L.append(f"| {c.ticker} | {c.direction or '—'} | {c.score:.0f} | {', '.join(c.sources)} | {decision} | "
                 f"{'; '.join(c.reasons[:5])} |")
    L += ["", "## Flux Unusual Whales utilisés", ""]
    for nom, etat in sorted(feeds.items()):
        L.append(f"- {nom} : {etat}")
    if erreurs:
        L += ["", "## Erreurs", ""] + [f"- {e}" for e in erreurs]
    L += ["", "_Les ordres sont transmis par le robot (executor) selon ses garde-fous ; en DRY_RUN rien n'est envoyé._"]
    return "\n".join(L) + "\n"


def ecrire_rapport(dossier: Path, quand: dt.datetime, desk: str, texte: str) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"{quand.strftime('%Y-%m-%d-%H%M')}-{desk}.md"
    f.write_text(texte, encoding="utf-8")
    (dossier / f"dernier-{desk}.md").write_text(texte, encoding="utf-8")
    return f
