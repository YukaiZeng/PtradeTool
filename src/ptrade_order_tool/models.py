from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


OrderType = Literal["buy_stop", "buy_limit", "sell_profit", "sell_loss"]
OrderSource = Literal["manual", "inherited"]
ExportState = Literal["empty", "draft", "exported", "modified_after_export"]


def calculate_next_trade_available_cash(portfolio_value: Decimal, stock_positions_value: Decimal) -> Decimal:
    return portfolio_value - stock_positions_value


@dataclass(slots=True)
class FundSnapshot:
    cash: Decimal
    positions_value: Decimal
    portfolio_value: Decimal
    stock_positions_value: Decimal
    next_trade_available_cash: Decimal


@dataclass(slots=True)
class Holding:
    ts_code: str
    stock_code: str
    stock_name: str
    current_amount: int
    enable_amount: int
    last_price: Decimal
    cost_price: Decimal
    market_value: Decimal
    profit_ratio: Decimal
    income_balance: Decimal
    is_stock: bool = True


@dataclass(slots=True)
class OrderDraft:
    order_type: OrderType
    price: Decimal
    shares: int
    confirmed: bool = False
    source: OrderSource = "manual"
    warning: str = ""
    id: int | None = None
    sort_order: int = 0


@dataclass(slots=True)
class StockDraft:
    ts_code: str
    stock_name: str
    is_holding: bool
    holding: Holding | None = None
    orders: list[OrderDraft] = field(default_factory=list)


@dataclass(slots=True)
class DailyQuote:
    ts_code: str
    trade_date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    pre_close: Decimal
    change: Decimal
    pct_chg: Decimal
    vol: Decimal
    amount: Decimal


@dataclass(slots=True)
class SessionDraft:
    manage_date: str
    expected_trade_date: str | None
    fund: FundSnapshot
    stocks: list[StockDraft]
    ptrade_json_path: str = ""
    export_json_path: str = ""
    export_state: ExportState = "draft"
    read_only: bool = False


@dataclass(slots=True)
class ImportedPtradeData:
    manage_date: str
    fund: FundSnapshot
    holdings: list[Holding]


@dataclass(slots=True)
class ExportValidation:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_export(self) -> bool:
        return not self.blockers
