import json
from decimal import Decimal
from pathlib import Path

import pytest

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.order_exporter import build_order_json, export_order_json, validate_export
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from tests.test_ptrade_importer import FakeStockMatcher


PTRADER_FIXTURE = Path(__file__).parent / "fixtures" / "ptrade_20260225.json"


def make_store_with_draft(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )
    return store, draft


def test_export_json_contains_only_clean_order_fields(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    store.confirm_order(order_id)
    draft = store.load_draft("20260225")

    data = build_order_json(draft)

    assert data == {
        "002153.SZ": {
            "stock_name": "石基信息",
            "buy_limit": [{"price": 11.4, "shares": 1400}],
        }
    }


def test_export_json_keeps_prices_numeric_without_string_formatting(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("5"), 1400)
    store.confirm_order(order_id)

    data = build_order_json(store.load_draft("20260225"))

    assert data["002153.SZ"]["buy_limit"] == [{"price": 5, "shares": 1400}]


def test_export_order_json_writes_standard_numeric_price(sqlite_conn, tmp_path):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("5"), 1400)
    store.confirm_order(order_id)
    output_path = tmp_path / "20260225.json"

    export_order_json(store.load_draft("20260225"), output_path)

    text = output_path.read_text(encoding="utf-8")
    assert '"price": 5' in text
    assert '"price": "5' not in text
    assert json.loads(text)["002153.SZ"]["buy_limit"][0]["price"] == 5


def test_unconfirmed_order_blocks_export(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    validation = validate_export(store.load_draft("20260225"))

    assert validation.can_export is False
    assert "未确认" in validation.blockers[0]


def test_invalid_price_and_shares_block_export(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.456"), 150)
    store.confirm_order(order_id)

    validation = validate_export(store.load_draft("20260225"))

    assert validation.can_export is False
    assert any("价格最多2位小数" in item for item in validation.blockers)
    assert any("100股整数倍" in item for item in validation.blockers)


def test_holding_sell_total_mismatch_warns_not_blocks(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    profit_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1400)
    loss_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_loss", Decimal("10.99"), 2800)
    store.confirm_order(profit_id)
    store.confirm_order(loss_id)

    validation = validate_export(store.load_draft("20260225"))

    assert validation.can_export is True
    assert any("止盈合计 1400 不等于可卖数量 2800" in item for item in validation.warnings)


def test_profit_price_below_loss_price_warns_not_blocks(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    profit_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("10.50"), 2800)
    loss_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_loss", Decimal("10.99"), 2800)
    store.confirm_order(profit_id)
    store.confirm_order(loss_id)

    validation = validate_export(store.load_draft("20260225"))

    assert validation.can_export is True
    assert any("止盈价格 10.50 小于止损价格 10.99" in item for item in validation.warnings)


def test_opening_sell_total_mismatch_warns_not_blocks(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    buy_id = store.add_order(draft.manage_date, "600000.SH", "浦发银行", "buy_stop", Decimal("10.00"), 1000)
    profit_id = store.add_order(draft.manage_date, "600000.SH", "浦发银行", "sell_profit", Decimal("11.00"), 500)
    store.confirm_order(buy_id)
    store.confirm_order(profit_id)

    validation = validate_export(store.load_draft("20260225"))

    assert validation.can_export is True
    assert any("止盈合计 500 不等于买单合计 1000" in item for item in validation.warnings)


def test_opening_stock_export_preserves_stock_name(sqlite_conn):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "600000.SH", "浦发银行", "buy_stop", Decimal("10.00"), 1000)
    store.confirm_order(order_id)

    data = build_order_json(store.load_draft("20260225"))

    assert data["600000.SH"]["stock_name"] == "浦发银行"


def test_export_requires_overwrite_permission(sqlite_conn, tmp_path):
    store, draft = make_store_with_draft(sqlite_conn)
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    store.confirm_order(order_id)
    output_path = tmp_path / "20260225.json"
    output_path.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_order_json(store.load_draft("20260225"), output_path)

    export_order_json(store.load_draft("20260225"), output_path, allow_overwrite=True)
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["002153.SZ"]["buy_limit"][0]["shares"] == 1400
