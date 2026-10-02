import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def ticket_dict(**k):
    d = {
        "id": "swing-2026-10-02-SMCI", "symbol": "SMCI", "direction": "up", "side": "BUY",
        "quantity": 1, "limit_price": 2.80, "price_cap": 3.00, "take_profit": 6.10, "stop_loss": 1.60,
        "max_loss": 160.0, "premium": 280.0,
        "legs": [{"expiry": "20261030", "strike": 39, "right": "C", "action": "BUY"},
                 {"expiry": "20261030", "strike": 47, "right": "C", "action": "SELL"}],
        "condition": {"op": ">=", "price": 42.10}, "underlying_stop": 38.0, "time_exit": "2026-10-23",
    }
    d.update(k)
    return d


@pytest.fixture
def jour():
    return dt.date(2026, 10, 2)
