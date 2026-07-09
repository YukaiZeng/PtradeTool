from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from ptrade_order_tool.models import (
    FundSnapshot,
    Holding,
    ImportedPtradeData,
    calculate_next_trade_available_cash,
)


class PtradeImportError(ValueError):
    pass


class StockMatcher(Protocol):
    def resolve_stock(self, query: str) -> dict[str, str] | None:
        """Return a stock row with ts_code/symbol/name, or None."""


def parse_ptrade_json(path: Path, stock_matcher: StockMatcher) -> ImportedPtradeData:
    data = json.loads(path.read_text(encoding="utf-8"))
    manage_date = _date_from_filename(path)

    fund_data = _require_mapping(data, "Fund")
    hold_data = _require_mapping(data, "Hold")

    raw_cash = _decimal_field(fund_data, "cash")
    raw_positions_value = _decimal_field(fund_data, "positions_value")
    raw_portfolio_value = _decimal_field(fund_data, "portfolio_value")

    holdings: list[Holding] = []
    stock_positions_value = Decimal("0")

    for raw_key, raw_holding in hold_data.items():
        if not isinstance(raw_holding, dict):
            raise PtradeImportError(f"Hold.{raw_key} must be an object")

        stock_code = str(raw_holding.get("stock_code", raw_key)).strip()
        stock_row = (
            stock_matcher.resolve_stock(str(raw_key))
            or stock_matcher.resolve_stock(stock_code)
            or _fallback_stock_row(str(raw_key), stock_code, raw_holding)
        )
        market_value = _decimal_value(raw_holding.get("market_value", 0))

        if not stock_row:
            continue

        holding = Holding(
            ts_code=str(stock_row["ts_code"]),
            stock_code=stock_code,
            stock_name=str(raw_holding.get("stock_name") or stock_row["name"]),
            current_amount=_int_amount(raw_holding.get("current_amount"), f"Hold.{raw_key}.current_amount"),
            enable_amount=_int_amount(raw_holding.get("enable_amount"), f"Hold.{raw_key}.enable_amount"),
            last_price=_decimal_value(raw_holding.get("last_price", 0)),
            cost_price=_decimal_value(raw_holding.get("cost_price", 0)),
            market_value=market_value,
            profit_ratio=_decimal_value(raw_holding.get("profit_ratio", 0)),
            income_balance=_decimal_value(raw_holding.get("income_balance", 0)),
            is_stock=True,
        )
        holdings.append(holding)
        stock_positions_value += holding.market_value

    fund = FundSnapshot(
        cash=raw_cash,
        positions_value=raw_positions_value,
        portfolio_value=raw_portfolio_value,
        stock_positions_value=stock_positions_value,
        next_trade_available_cash=calculate_next_trade_available_cash(raw_portfolio_value, stock_positions_value),
    )
    return ImportedPtradeData(manage_date=manage_date, fund=fund, holdings=holdings)


def _date_from_filename(path: Path) -> str:
    match = re.search(r"(\d{8})", path.stem)
    if not match:
        raise PtradeImportError(f"Ptrade JSON filename must be YYYYMMDD: {path.name}")
    return match.group(1)


def _require_mapping(data: Any, key: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PtradeImportError("Ptrade JSON root must be an object")
    value = data.get(key)
    if not isinstance(value, dict):
        raise PtradeImportError(f"Ptrade JSON missing object field: {key}")
    return value


def _decimal_field(data: dict[str, Any], key: str) -> Decimal:
    if key not in data:
        raise PtradeImportError(f"Fund missing field: {key}")
    return _decimal_value(data[key])


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise PtradeImportError(f"Invalid decimal value: {value!r}") from exc


def _int_amount(value: Any, field_name: str) -> int:
    if value is None:
        raise PtradeImportError(f"{field_name} is required")
    decimal_value = _decimal_value(value)
    if decimal_value < 0 or decimal_value != decimal_value.to_integral_value():
        raise PtradeImportError(f"{field_name} must be a non-negative integer")
    return int(decimal_value)


def _fallback_stock_row(raw_key: str, stock_code: str, raw_holding: dict[str, Any]) -> dict[str, str] | None:
    stock_name = str(raw_holding.get("stock_name") or "").strip()
    stock_type = str(raw_holding.get("stock_type", "")).strip()
    if stock_type == "9" or "标准券" in stock_name:
        return None
    symbol = _symbol_from_code(stock_code or raw_key)
    if not symbol:
        return None
    suffix = _market_suffix(symbol)
    if not suffix:
        return None
    return {
        "ts_code": f"{symbol}.{suffix}",
        "symbol": symbol,
        "name": stock_name or symbol,
    }


def _symbol_from_code(code: str) -> str:
    text = code.strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text if re.fullmatch(r"\d{6}", text) else ""


def _market_suffix(symbol: str) -> str:
    if symbol.startswith(("00", "30")):
        return "SZ"
    if symbol.startswith(("60", "68")):
        return "SH"
    if symbol.startswith(("83", "87", "92")):
        return "BJ"
    return ""
