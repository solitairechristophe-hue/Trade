"""Configuration lue dans les variables d'environnement (fichier .env du docker compose)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(nom: str, defaut: bool) -> bool:
    v = os.environ.get(nom)
    if v is None or v == "":
        return defaut
    return v.strip().lower() in ("1", "true", "yes", "oui", "on")


def _float(nom: str, defaut: float) -> float:
    v = os.environ.get(nom)
    return float(v) if v not in (None, "") else defaut


def _int(nom: str, defaut: int) -> int:
    v = os.environ.get(nom)
    return int(v) if v not in (None, "") else defaut


@dataclass(frozen=True)
class Config:
    # Connexion à IB Gateway
    ib_host: str = "ib-gateway"
    ib_port: int = 4003
    ib_client_id: int = 17
    account_id: str = ""  # obligatoire : le robot refuse de trader sur un autre compte

    # Sécurité
    dry_run: bool = True  # par défaut : simulation, aucun ordre transmis
    kill_switch_file: Path = Path("/data/STOP")

    # Limites de risque (fractions de la NAV)
    risk_per_trade: float = 0.02
    risk_tolerance: float = 0.10  # +10 % toléré au-dessus des 2 % (arrondi au contrat)
    max_premium_per_trade: float = 0.03
    max_total_risk: float = 0.10
    max_new_orders_per_day: int = 3
    max_contracts_per_order: int = 5

    # Fonctionnement
    tickets_dir: Path = Path("/tickets")
    git_pull: bool = False
    state_file: Path = Path("/data/etat.sqlite")
    poll_seconds: int = 60
    exit_reprice_loops: int = 3  # boucles avant de recoter un ordre de sortie non exécuté
    ntfy_url: str = ""

    @classmethod
    def depuis_env(cls) -> "Config":
        return cls(
            ib_host=os.environ.get("IB_HOST", cls.ib_host),
            ib_port=_int("IB_PORT", cls.ib_port),
            ib_client_id=_int("IB_CLIENT_ID", cls.ib_client_id),
            account_id=os.environ.get("IB_ACCOUNT_ID", ""),
            dry_run=_bool("DRY_RUN", True),
            kill_switch_file=Path(os.environ.get("KILL_SWITCH_FILE", str(cls.kill_switch_file))),
            risk_per_trade=_float("RISK_PER_TRADE", cls.risk_per_trade),
            risk_tolerance=_float("RISK_TOLERANCE", cls.risk_tolerance),
            max_premium_per_trade=_float("MAX_PREMIUM_PER_TRADE", cls.max_premium_per_trade),
            max_total_risk=_float("MAX_TOTAL_RISK", cls.max_total_risk),
            max_new_orders_per_day=_int("MAX_NEW_ORDERS_PER_DAY", cls.max_new_orders_per_day),
            max_contracts_per_order=_int("MAX_CONTRACTS_PER_ORDER", cls.max_contracts_per_order),
            tickets_dir=Path(os.environ.get("TICKETS_DIR", str(cls.tickets_dir))),
            git_pull=_bool("GIT_PULL", False),
            state_file=Path(os.environ.get("STATE_FILE", str(cls.state_file))),
            poll_seconds=_int("POLL_SECONDS", cls.poll_seconds),
            exit_reprice_loops=_int("EXIT_REPRICE_LOOPS", cls.exit_reprice_loops),
            ntfy_url=os.environ.get("NTFY_URL", ""),
        )
