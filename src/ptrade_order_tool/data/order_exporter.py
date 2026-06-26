from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from ptrade_order_tool.models import ExportValidation, OrderDraft, SessionDraft, StockDraft


ORDER_TYPES = ("buy_stop", "buy_limit", "sell_profit", "sell_loss")


def validate_export(draft: SessionDraft) -> ExportValidation:
    validation = ExportValidation()

    for stock in draft.stocks:
        if any(not order.confirmed for order in stock.orders):
            validation.blockers.append(f"{stock.ts_code} {stock.stock_name} 存在未确认订单")

        for order in stock.orders:
            if order.confirmed:
                _validate_order(stock, order, validation)

        confirmed = [order for order in stock.orders if order.confirmed]
        if not confirmed:
            continue

        if stock.is_holding and stock.holding:
            _validate_holding_totals(stock, confirmed, validation)
        else:
            _validate_opening_totals(stock, confirmed, validation)
        _validate_profit_loss_prices(stock, confirmed, validation)

    return validation


def build_order_json(draft: SessionDraft) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for stock in draft.stocks:
        confirmed = [order for order in stock.orders if order.confirmed]
        if not confirmed:
            continue
        stock_data: dict[str, object] = {"stock_name": stock.stock_name}
        for order_type in ORDER_TYPES:
            items = [
                {"price": _json_price(order.price), "shares": order.shares}
                for order in confirmed
                if order.order_type == order_type
            ]
            if items:
                stock_data[order_type] = items
        result[stock.ts_code] = stock_data
    return result


def export_order_json(draft: SessionDraft, output_path: Path, *, allow_overwrite: bool = False) -> None:
    validation = validate_export(draft)
    if not validation.can_export:
        raise ValueError("; ".join(validation.blockers))
    if output_path.exists() and not allow_overwrite:
        raise FileExistsError(str(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_order_json(draft), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_order(stock: StockDraft, order: OrderDraft, validation: ExportValidation) -> None:
    if order.price <= 0:
        validation.blockers.append(f"{stock.ts_code} {stock.stock_name} 订单价格必须大于0")
    if -order.price.as_tuple().exponent > 2:
        validation.blockers.append(f"{stock.ts_code} {stock.stock_name} 订单价格最多2位小数")
    if order.shares <= 0 or order.shares % 100 != 0:
        validation.blockers.append(f"{stock.ts_code} {stock.stock_name} 订单数量必须为100股整数倍")


def _validate_holding_totals(
    stock: StockDraft,
    confirmed: list[OrderDraft],
    validation: ExportValidation,
) -> None:
    holding_amount = stock.holding.current_amount if stock.holding else 0
    profit_total = sum(order.shares for order in confirmed if order.order_type == "sell_profit")
    loss_total = sum(order.shares for order in confirmed if order.order_type == "sell_loss")
    if profit_total != holding_amount:
        validation.warnings.append(
            f"{stock.ts_code} {stock.stock_name} 止盈合计 {_format_shares(profit_total)} 不等于持仓数量 {_format_shares(holding_amount)}"
        )
    if loss_total != holding_amount:
        validation.warnings.append(
            f"{stock.ts_code} {stock.stock_name} 止损合计 {_format_shares(loss_total)} 不等于持仓数量 {_format_shares(holding_amount)}"
        )


def _validate_opening_totals(
    stock: StockDraft,
    confirmed: list[OrderDraft],
    validation: ExportValidation,
) -> None:
    buy_total = sum(order.shares for order in confirmed if order.order_type in {"buy_stop", "buy_limit"})
    profit_total = sum(order.shares for order in confirmed if order.order_type == "sell_profit")
    loss_total = sum(order.shares for order in confirmed if order.order_type == "sell_loss")

    if buy_total == 0 and (profit_total or loss_total):
        validation.warnings.append(f"{stock.ts_code} {stock.stock_name} 无买单但存在卖单计划")
    if (buy_total or profit_total) and profit_total != buy_total:
        validation.warnings.append(
            f"{stock.ts_code} {stock.stock_name} 止盈合计 {_format_shares(profit_total)} 不等于买单合计 {_format_shares(buy_total)}"
        )
    if (buy_total or loss_total) and loss_total != buy_total:
        validation.warnings.append(
            f"{stock.ts_code} {stock.stock_name} 止损合计 {_format_shares(loss_total)} 不等于买单合计 {_format_shares(buy_total)}"
        )


def _validate_profit_loss_prices(
    stock: StockDraft,
    confirmed: list[OrderDraft],
    validation: ExportValidation,
) -> None:
    profit_orders = [order for order in confirmed if order.order_type == "sell_profit"]
    loss_orders = [order for order in confirmed if order.order_type == "sell_loss"]
    for profit_order in profit_orders:
        for loss_order in loss_orders:
            if profit_order.price < loss_order.price:
                validation.warnings.append(
                    f"{stock.ts_code} {stock.stock_name} 止盈价格 {profit_order.price:.2f} 小于止损价格 {loss_order.price:.2f}"
                )


def _json_price(price: Decimal) -> int | float:
    normalized = price.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(price)


def _format_shares(shares: int) -> str:
    return f"{shares:,}"
