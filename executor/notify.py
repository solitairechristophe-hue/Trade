"""Notifications : journal standard et, si NTFY_URL est défini, push sur le téléphone (ntfy.sh)."""
from __future__ import annotations

import logging
import urllib.request

log = logging.getLogger("robot")


class Notifier:
    def __init__(self, ntfy_url: str = ""):
        self.ntfy_url = ntfy_url

    def __call__(self, message: str, urgent: bool = False) -> None:
        log.warning(message) if urgent else log.info(message)
        if not self.ntfy_url:
            return
        try:
            req = urllib.request.Request(self.ntfy_url, data=message.encode("utf-8"), method="POST",
                                         headers={"Title": "Robot IBKR", "Priority": "high" if urgent else "default"})
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as e:  # une notification ratée ne doit jamais arrêter le robot
            log.error("notification impossible : %s", e)
