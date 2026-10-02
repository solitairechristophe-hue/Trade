"""Un scan : flux Unusual Whales → régime → candidats → enrichissement → score → structure → sizing → tickets.

`feeds` est n'importe quel objet exposant les méthodes de UwClient (les tests injectent un faux).
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .config import ScanConfig
from .model import Regime
from .output import ecrire_rapport, ecrire_tickets, rapport_markdown, ticket_id, vers_ticket
from .regime import build_regime
from .scoring import Candidate, noter, preselection, regrouper
from .sizing import Dimensionnee, charger_calibration, classer, dimensionner
from .state import EtatScanner
from .structure import proposer

NY = ZoneInfo("America/New_York")
log = logging.getLogger("scanner")


@dataclass
class Resultat:
    quand: dt.datetime
    regime: Regime
    nav: float
    retenus: list[Dimensionnee] = field(default_factory=list)
    etudies: list[tuple[Candidate, str]] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)
    feeds: dict[str, str] = field(default_factory=dict)
    erreurs: list[str] = field(default_factory=list)
    rapport: str = ""


def _collecte(feeds, nom: str, fn, res: Resultat, defaut):
    try:
        v = fn()
        n = len(v) if hasattr(v, "__len__") else 1
        res.feeds[nom] = f"ok ({n})"
        return v
    except Exception as e:
        res.feeds[nom] = f"échec : {e.__class__.__name__}"
        res.erreurs.append(f"{nom} : {e}")
        log.warning("flux %s en échec : %s", nom, e)
        return defaut


def seance_ouverte(m: dt.datetime) -> bool:
    return m.weekday() < 5 and dt.time(9, 30) <= m.time() < dt.time(16, 0)


def scan(cfg: ScanConfig, feeds, nav: float, positions: set[str], now: dt.datetime,
         etat: EtatScanner | None = None, ecrire: bool = True) -> Resultat:
    now = now.astimezone(NY) if now.tzinfo else now.replace(tzinfo=NY)
    today = now.date()
    res = Resultat(quand=now, regime=Regime(), nav=nav)
    if nav <= 0:
        res.erreurs.append("NAV inconnue : aucun ticket ne peut être dimensionné")

    # 1. régime de marché (flux globaux)
    tide = _collecte(feeds, "market tide", feeds.market_tide, res, [])
    secteurs = _collecte(feeds, "sector tide (11 secteurs)", feeds.sector_tides, res, {})
    spy_gex = _collecte(feeds, "SPY greek exposure", feeds.spy_gex_net, res, None)
    events = _collecte(feeds, "economic calendar", feeds.economic_calendar, res, [])
    res.regime = build_regime(tide, secteurs, spy_gex, events, now, market_closed=not seance_ouverte(now))

    # 2. candidats (tous les flux de découverte)
    depuis = now - dt.timedelta(minutes=cfg.lookback_minutes)
    if not seance_ouverte(now):  # avant l'ouverture : flux de la veille entière
        depuis = now - dt.timedelta(hours=20)
    alerts = _collecte(feeds, "flow alerts", lambda: feeds.flow_alerts(depuis), res, [])
    screener = _collecte(feeds, "options screener (hottest chains)", feeds.screener_hits, res, [])
    dark = _collecte(feeds, "dark pool recent", feeds.dark_pool_recent, res, [])
    oi = _collecte(feeds, "market OI change", feeds.market_oi_changes, res, [])
    insiders = _collecte(feeds, "insider transactions", feeds.insider_recent, res, [])
    congress = _collecte(feeds, "congress trades", feeds.congress_recent, res, [])
    cands = regrouper(alerts, screener, dark, oi, insiders, congress)

    # 3. univers
    exclus = set(positions) | set(cfg.exclude_symbols)
    if etat:
        exclus |= etat.symboles_recents(today, cfg.cooldown_days)
    for tk in list(cands):
        c = cands[tk]
        if tk in exclus or not tk or not tk.isalpha():
            del cands[tk]
            continue
        if c.alerts:  # métadonnées disponibles sans appel supplémentaire
            a = c.alerts[0]
            if a.issue_type and a.issue_type not in cfg.issue_types:
                del cands[tk]
                continue
            if a.marketcap and a.marketcap < cfg.min_marketcap and a.issue_type != "ETF":
                del cands[tk]
                continue
            if a.underlying_price and not cfg.min_stock_price <= a.underlying_price <= cfg.max_stock_price:
                del cands[tk]
                continue
        elif not (c.screener or c.oi_changes):
            del cands[tk]  # dark pool / initiés / congrès seuls ne suffisent pas à ouvrir un dossier

    # 4. enrichissement + scoring des plus chauds
    pre = preselection(cands, cfg.max_candidates)
    res.feeds["enrichissement par titre (15 flux × candidats)"] = f"{len(pre)} titres"
    notes: list[Candidate] = []
    for c in pre:
        try:
            c.context = feeds.enrich(c.ticker, today, cfg.min_dte, cfg.max_dte)
        except Exception as e:
            res.erreurs.append(f"{c.ticker} : enrichissement impossible ({e})")
            c.context = None
        noter(c, res.regime, today, cfg.max_dte)
        notes.append(c)
    notes.sort(key=lambda c: c.score, reverse=True)

    # 5. structure, sizing, classement
    calib = charger_calibration(cfg.calibration_file)
    res.feeds["calibration de p"] = f"{calib[0]:.2f}–{calib[1]:.2f} (mesurée)" if calib else "défaut 0,38–0,62 (non mesurée)"
    quota_jour = cfg.max_new_orders_per_day - (etat.tickets_du_jour(today) if etat else 0)
    budget_risque_total = nav * cfg.max_total_risk
    dims: list[tuple[Candidate, Dimensionnee]] = []
    for c in notes:
        ctx = c.context
        if not c.direction or c.score < cfg.min_score:
            res.etudies.append((c, f"écarté : score {c.score:.0f} < {cfg.min_score:.0f}" if c.direction else "écarté : sans direction"))
            continue
        if res.regime.risk_off:
            res.etudies.append((c, "écarté : risk-off (événement macro imminent)"))
            continue
        if ctx is None or not ctx.price:
            res.etudies.append((c, "écarté : pas de données de prix"))
            continue
        if not cfg.min_stock_price <= ctx.price <= cfg.max_stock_price or (ctx.marketcap and ctx.marketcap < cfg.min_marketcap):
            res.etudies.append((c, "écarté : hors univers (prix ou capitalisation)"))
            continue
        prop = proposer(ctx, c.direction, today, min_dte=cfg.min_dte, max_dte=cfg.max_dte,
                        long_delta=cfg.long_delta, short_delta=cfg.short_delta, iv_rank_credit=cfg.iv_rank_credit,
                        tp_fraction=cfg.tp_fraction, sl_fraction=cfg.sl_fraction,
                        max_premium=nav * cfg.max_premium_per_trade if nav > 0 else 1e9,
                        hold_days=cfg.hold_days)
        if prop is None:
            res.etudies.append((c, "écarté : aucune structure liquide/abordable dans la fenêtre d'échéances"))
            continue
        d = dimensionner(prop, c.score, nav, risk_per_trade=cfg.risk_per_trade,
                         max_premium_per_trade=cfg.max_premium_per_trade, max_contracts=cfg.max_contracts_per_order,
                         risque_restant=budget_risque_total, calib=calib)
        if d is None:
            res.etudies.append((c, "écarté : risque par contrat > budget (2 % de la NAV)"))
            continue
        if d.ev <= 0:
            res.etudies.append((c, f"écarté : espérance négative ({d.ev:+.0f} $)"))
            continue
        dims.append((c, d))

    classes = classer([d for _, d in dims])
    par_prop = {id(d): c for c, d in dims}
    limite = max(0, min(cfg.max_tickets_per_run, quota_jour))
    for i, d in enumerate(classes):
        c = par_prop[id(d)]
        if i < limite:
            res.retenus.append(d)
            res.etudies.append((c, f"RETENU #{i + 1} : {d.prop.strategy}, EV {d.ev:+.0f} $ ({d.ev_ratio:+.2f}/$ risqué)"))
        else:
            res.etudies.append((c, f"candidat valable mais hors quota (EV {d.ev:+.0f} $)"))
    res.etudies.sort(key=lambda cd: cd[0].score, reverse=True)

    # 6. sorties
    res.tickets = [vers_ticket(d, cfg.desk, today) for d in res.retenus]
    res.rapport = rapport_markdown(now, res.regime, nav, res.retenus, res.etudies, res.feeds, res.erreurs)
    if ecrire:
        if res.tickets:
            ecrire_tickets(cfg.tickets_dir, cfg.desk, today, res.tickets)
        ecrire_rapport(cfg.reports_dir, now, cfg.desk, res.rapport)
        if etat:
            for d in res.retenus:
                etat.enregistrer(ticket_id(cfg.desk, today, d.prop.symbol), d.prop.symbol, d.prop.direction, now,
                                 d.score, d.ev, d.quantity, d.prop.note)
            etat.journal(now, len(cands), len(res.tickets), res.erreurs)
    return res
