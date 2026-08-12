from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ptrade_order_tool.models import OrderDraft


def order_price_violations(orders: Iterable[OrderDraft], close: Decimal | None) -> list[str]:
    if close is None:
        return []

    violations: list[str] = []
    for order in orders:
        if order.order_type == "buy_stop" and order.price < close:
            violations.append(f"突破买价格 {order.price:.2f} 低于收盘价 {close:.2f}（阻断）")
        elif order.order_type == "buy_limit" and order.price >= close:
            violations.append(f"回调买价格 {order.price:.2f} 不小于收盘价 {close:.2f}（阻断）")
        elif order.order_type == "sell_profit" and order.price < close:
            violations.append(f"止盈价格 {order.price:.2f} 低于收盘价 {close:.2f}（阻断）")
        elif order.order_type == "sell_loss" and order.price >= close:
            violations.append(f"止损价格 {order.price:.2f} 不小于收盘价 {close:.2f}（阻断）")
    return violations


def buy_price_violations(orders: Iterable[OrderDraft], close: Decimal | None) -> list[str]:
    return order_price_violations(orders, close)
