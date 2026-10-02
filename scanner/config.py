"""Configuration du scanner (variables d'environnement, fichier .env du docker compose)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(nom: str, defaut: bool) -> bool:
    v = os.environ.get(nom)
    if v in (None, ""):
        return defaut
    return v.strip().lower() in ("1", "true", "yes", "oui", "on")


def _float(nom: str, defaut: float) -> float:
    v = os.environ.get(nom)
    return float(v) if v not in (None, "") else defaut


def _int(nom: str, defaut: int) -> int:
    v = os.environ.get(nom)
    return int(v) if v not in (None, "") else defaut


def _liste(nom: str, defaut: tuple[str, ...]) -> tuple[str, ...]:
    v = os.environ.get(nom)
    if v in (None, ""):
        return defaut
    return tuple(x.strip().upper() for x in v.split(",") if x.strip())


@dataclass(frozen=True)
class ScanConfig:
    # Unusual Whales (API REST publique : https://api.unusualwhales.com/docs)
    uw_token: str = ""
    uw_base_url: str = "https://api.unusualwhales.com"
    uw_timeout: float = 20.0

    # IBKR : NAV et positions ouvertes (facultatif : repli sur NAV_USD)
    ib_host: str = "ib-gateway"
    ib_port: int = 4003
    ib_client_id: int = 18
    account_id: str = ""
    nav_usd: float = 0.0  # repli si IB Gateway est injoignable

    # Sorties
    desk: str = "flow"
    tickets_dir: Path = Path("/tickets")
    reports_dir: Path = Path("/reports")
    state_file: Path = Path("/data/scanner.sqlite")
    kill_switch_file: Path = Path("/data/STOP")
    ntfy_url: str = ""

    # Garde-fous (identiques à ceux du robot : un ticket hors limite serait refusé)
    risk_per_trade: float = 0.02
    max_premium_per_trade: float = 0.03
    max_total_risk: float = 0.10
    max_new_orders_per_day: int = 3
    max_contracts_per_order: int = 5
    max_tickets_per_run: int = 3

    # Univers et sélection
    lookback_minutes: int = 90  # fenêtre de flux analysée à chaque heure
    min_score: float = 55.0
    min_premium_alert: float = 50_000.0
    min_marketcap: float = 2_000_000_000.0
    min_stock_price: float = 8.0
    max_stock_price: float = 1500.0
    max_candidates: int = 15  # tickers enrichis (appels API) par run
    exclude_symbols: tuple[str, ...] = ()
    issue_types: tuple[str, ...] = ("Common Stock", "ADR", "ETF")

    # Structure des trades
    min_dte: int = 21
    max_dte: int = 50
    long_delta: float = 0.50
    short_delta: float = 0.25
    iv_rank_credit: float = 0.55  # au-dessus : spread crédit plutôt que débit
    tp_fraction: float = 0.55  # part du gain maximal visée (débit)
    sl_fraction: float = 0.50  # part de la prime perdue avant sortie (débit)
    cooldown_days: int = 3  # pas de nouveau ticket sur un titre déjà proposé récemment

    # Planification (heure de New York)
    scan_hours: tuple[int, ...] = (9, 10, 11, 12, 13, 14, 15)
    scan_minute: int = 5
    seasonality_feeds: bool = True

    @classmethod
    def depuis_env(cls) -> "ScanConfig":
        return cls(
            uw_token=os.environ.get("UW_TOKEN", ""),
            uw_base_url=os.environ.get("UW_BASE_URL", cls.uw_base_url).rstrip("/"),
            uw_timeout=_float("UW_TIMEOUT", cls.uw_timeout),
            ib_host=os.environ.get("IB_HOST", cls.ib_host),
            ib_port=_int("IB_PORT", cls.ib_port),
            ib_client_id=_int("SCANNER_IB_CLIENT_ID", cls.ib_client_id),
            account_id=os.environ.get("IB_ACCOUNT_ID", ""),
            nav_usd=_float("NAV_USD", 0.0),
            desk=os.environ.get("SCANNER_DESK", cls.desk),
            tickets_dir=Path(os.environ.get("TICKETS_DIR", str(cls.tickets_dir))),
            reports_dir=Path(os.environ.get("REPORTS_DIR", str(cls.reports_dir))),
            state_file=Path(os.environ.get("SCANNER_STATE_FILE", str(cls.state_file))),
            kill_switch_file=Path(os.environ.get("KILL_SWITCH_FILE", str(cls.kill_switch_file))),
            ntfy_url=os.environ.get("NTFY_URL", ""),
            risk_per_trade=_float("RISK_PER_TRADE", cls.risk_per_trade),
            max_premium_per_trade=_float("MAX_PREMIUM_PER_TRADE", cls.max_premium_per_trade),
            max_total_risk=_float("MAX_TOTAL_RISK", cls.max_total_risk),
            max_new_orders_per_day=_int("MAX_NEW_ORDERS_PER_DAY", cls.max_new_orders_per_day),
            max_contracts_per_order=_int("MAX_CONTRACTS_PER_ORDER", cls.max_contracts_per_order),
            max_tickets_per_run=_int("MAX_TICKETS_PER_RUN", cls.max_tickets_per_run),
            lookback_minutes=_int("LOOKBACK_MINUTES", cls.lookback_minutes),
            min_score=_float("MIN_SCORE", cls.min_score),
            min_premium_alert=_float("MIN_PREMIUM_ALERT", cls.min_premium_alert),
            min_marketcap=_float("MIN_MARKETCAP", cls.min_marketcap),
            min_stock_price=_float("MIN_STOCK_PRICE", cls.min_stock_price),
            max_stock_price=_float("MAX_STOCK_PRICE", cls.max_stock_price),
            max_candidates=_int("MAX_CANDIDATES", cls.max_candidates),
            exclude_symbols=_liste("EXCLUDE_SYMBOLS", cls.exclude_symbols),
            min_dte=_int("MIN_DTE", cls.min_dte),
            max_dte=_int("MAX_DTE", cls.max_dte),
            iv_rank_credit=_float("IV_RANK_CREDIT", cls.iv_rank_credit),
            cooldown_days=_int("COOLDOWN_DAYS", cls.cooldown_days),
            scan_minute=_int("SCAN_MINUTE", cls.scan_minute),
        )
