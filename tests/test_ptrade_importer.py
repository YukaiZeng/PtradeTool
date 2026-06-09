import json
from decimal import Decimal
from pathlib import Path

import pytest

from ptrade_order_tool.data.ptrade_importer import PtradeImportError, parse_ptrade_json


FIXTURE = Path(__file__).parent / "fixtures" / "ptrade_20260225.json"


class FakeStockMatcher:
    rows = {
        "002153": {"ts_code": "002153.SZ", "symbol": "002153", "name": "石基信息"},
        "002153.SZ": {"ts_code": "002153.SZ", "symbol": "002153", "name": "石基信息"},
        "300162": {"ts_code": "300162.SZ", "symbol": "300162", "name": "雷曼光电"},
        "300162.SZ": {"ts_code": "300162.SZ", "symbol": "300162", "name": "雷曼光电"},
        "300251": {"ts_code": "300251.SZ", "symbol": "300251", "name": "光线传媒"},
        "300251.SZ": {"ts_code": "300251.SZ", "symbol": "300251", "name": "光线传媒"},
        "600000": {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
        "600000.SH": {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
    }

    def resolve_stock(self, query: str):
        return self.rows.get(query)


class EmptyStockMatcher:
    def resolve_stock(self, query: str):
        return None


def test_parse_ptrade_json_calibrates_account_values():
    result = parse_ptrade_json(FIXTURE, FakeStockMatcher())

    assert result.manage_date == "20260225"
    assert result.fund.cash == Decimal("361.86")
    assert result.fund.positions_value == Decimal("88020.0")
    assert result.fund.portfolio_value == Decimal("88381.86")
    assert result.fund.stock_positions_value == Decimal("55020.0")
    assert result.fund.calibrated_cash == Decimal("33361.86")


def test_parse_ptrade_json_filters_non_stock_assets():
    result = parse_ptrade_json(FIXTURE, FakeStockMatcher())

    assert [holding.ts_code for holding in result.holdings] == [
        "002153.SZ",
        "300162.SZ",
        "300251.SZ",
    ]
    assert all(holding.stock_name != "标准券" for holding in result.holdings)


def test_parse_ptrade_json_falls_back_to_ptrade_stock_fields_when_stock_cache_empty():
    result = parse_ptrade_json(FIXTURE, EmptyStockMatcher())

    assert [holding.ts_code for holding in result.holdings] == [
        "002153.SZ",
        "300162.SZ",
        "300251.SZ",
    ]
    assert result.fund.stock_positions_value == Decimal("55020.0")
    assert result.fund.calibrated_cash == Decimal("33361.86")


def test_parse_ptrade_json_converts_amounts_to_ints():
    result = parse_ptrade_json(FIXTURE, FakeStockMatcher())

    shiji = next(holding for holding in result.holdings if holding.ts_code == "002153.SZ")
    assert shiji.current_amount == 2800
    assert shiji.enable_amount == 2800


def test_parse_ptrade_json_rejects_missing_fund(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.pop("Fund")
    path = tmp_path / "20260225.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PtradeImportError, match="Fund"):
        parse_ptrade_json(path, FakeStockMatcher())


def test_parse_ptrade_json_rejects_missing_hold(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.pop("Hold")
    path = tmp_path / "20260225.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PtradeImportError, match="Hold"):
        parse_ptrade_json(path, FakeStockMatcher())
