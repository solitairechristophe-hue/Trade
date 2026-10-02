"""Accès IBKR via IB Gateway (API TWS, bibliothèque ib_async)."""
from __future__ import annotations

import logging

from ib_async import IB, Bag, ComboLeg, Contract, LimitOrder, Option, PriceCondition, Stock

from .tickets import Ticket

log = logging.getLogger("robot")
TERMINES = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}


class IbBroker:
    def __init__(self, ib: IB, compte: str):
        self.ib = ib
        self.compte = compte
        self._contrats: dict[str, Contract] = {}
        self._actions: dict[str, Contract] = {}
        self._flux: dict[int, object] = {}

    # --- compte -----------------------------------------------------------
    def verifier_compte(self) -> None:
        comptes = self.ib.managedAccounts()
        if self.compte not in comptes:
            raise RuntimeError(f"Compte {self.compte} absent de la session IB Gateway ({comptes})")

    def nav(self) -> float:
        for v in self.ib.accountSummary(self.compte):
            if v.tag == "NetLiquidation" and v.currency in ("USD", "BASE"):
                return float(v.value)
        return 0.0

    # --- contrats ---------------------------------------------------------
    def action(self, symbole: str) -> Contract:
        if symbole not in self._actions:
            (c,) = self.ib.qualifyContracts(Stock(symbole, "SMART", "USD"))
            self._actions[symbole] = c
        return self._actions[symbole]

    def contrat(self, t: Ticket) -> Contract:
        if t.id in self._contrats:
            return self._contrats[t.id]
        options = [Option(t.symbol, j.expiry, j.strike, j.right, "SMART", "100", "USD") for j in t.legs]
        qualifies = self.ib.qualifyContracts(*options)
        if len(qualifies) != len(options) or any(not o.conId for o in qualifies):
            raise RuntimeError(f"{t.id} : contrat d'option introuvable chez IBKR")
        if len(t.legs) == 1:
            c: Contract = qualifies[0]
        else:
            c = Bag(symbol=t.symbol, exchange="SMART", currency="USD", comboLegs=[
                ComboLeg(conId=o.conId, ratio=j.ratio, action=j.action, exchange="SMART")
                for o, j in zip(qualifies, t.legs)])
        self._contrats[t.id] = c
        return c

    # --- ordres -----------------------------------------------------------
    def _trade(self, ref: str):
        for tr in reversed(self.ib.trades()):
            if tr.order.orderRef == ref:
                return tr
        return None

    def statut(self, ref: str) -> tuple[str, float] | None:
        tr = self._trade(ref)
        if tr is None:
            return None
        return tr.orderStatus.status, float(tr.orderStatus.avgFillPrice or 0)

    def placer_entree(self, t: Ticket, ref_entree: str, ref_tp: str) -> None:
        c = self.contrat(t)
        if len(t.legs) == 1 and t.legs[0].action == "SELL":
            raise RuntimeError(f"{t.id} : vente d'option nue refusée par le robot")
        parent = LimitOrder(t.side, t.quantity, t.limit_price, tif="DAY", orderRef=ref_entree,
                            account=self.compte, transmit=False, orderId=self.ib.client.getReqId())
        if t.condition:
            parent.conditions = [PriceCondition(isMore=t.condition.op == ">=", price=t.condition.price,
                                                conId=self.action(t.symbol).conId, exch="SMART")]
        tp = LimitOrder(t.exit_side, t.quantity, t.take_profit, tif="GTC", orderRef=ref_tp,
                        account=self.compte, parentId=parent.orderId, transmit=True)
        self.ib.placeOrder(c, parent)
        self.ib.placeOrder(c, tp)

    def placer_sortie(self, t: Ticket, prix: float, ref: str) -> None:
        self.ib.placeOrder(self.contrat(t), LimitOrder(t.exit_side, t.quantity, prix, tif="DAY",
                                                       orderRef=ref, account=self.compte))

    def annuler(self, ref: str) -> None:
        tr = self._trade(ref)
        if tr is not None and tr.orderStatus.status not in TERMINES:
            self.ib.cancelOrder(tr.order)

    # --- cotations --------------------------------------------------------
    def _ticker(self, c: Contract):
        cle = id(c)
        if cle not in self._flux:
            self._flux[cle] = self.ib.reqMktData(c, "", False, False)
            self.ib.sleep(2)
        return self._flux[cle]

    def cotation(self, t: Ticket) -> tuple[float | None, float | None]:
        tk = self._ticker(self.contrat(t))
        return _num(tk.bid), _num(tk.ask)

    def cours(self, symbole: str) -> float | None:
        return _num(self._ticker(self.action(symbole)).marketPrice())


def _num(x) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x or x <= 0 else x  # NaN ou -1 = pas de cotation
