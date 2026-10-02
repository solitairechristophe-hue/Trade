"""NAV et positions IBKR via IB Gateway (ib_async), avec repli sur NAV_USD."""
from __future__ import annotations

import logging

from .config import ScanConfig

log = logging.getLogger("scanner")


def nav_et_positions(cfg: ScanConfig) -> tuple[float, set[str], str]:
    """Renvoie (NAV, symboles en position, source)."""
    try:
        from ib_async import IB
        ib = IB()
        ib.connect(cfg.ib_host, cfg.ib_port, clientId=cfg.ib_client_id, timeout=15, readonly=True)
        try:
            nav = 0.0
            for v in ib.accountSummary(cfg.account_id or ""):
                if v.tag == "NetLiquidation" and v.currency in ("USD", "BASE"):
                    nav = float(v.value)
            symboles = {p.contract.symbol for p in ib.positions() if p.position}
            if nav > 0:
                return nav, symboles, "IB Gateway"
        finally:
            ib.disconnect()
    except Exception as e:  # Gateway absent, 2FA en attente, module manquant…
        log.warning("NAV IBKR indisponible (%s)", e)
    if cfg.nav_usd > 0:
        return cfg.nav_usd, set(), "NAV_USD (repli)"
    return 0.0, set(), "inconnue"
