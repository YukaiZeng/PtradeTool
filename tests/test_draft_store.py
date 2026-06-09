from decimal import Decimal
from pathlib import Path

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from tests.test_ptrade_importer import FakeStockMatcher


PTRADER_FIXTURE = Path(__file__).parent / "fixtures" / "ptrade_20260225.json"
PREVIOUS_ORDER = Path(__file__).parent / "fixtures" / "order_20260224.json"


def create_imported():
    return parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())


def test_create_draft_imports_holdings_and_inherits_only_sell_orders(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
        previous_order_path=PREVIOUS_ORDER,
    )

    shiji = next(stock for stock in draft.stocks if stock.ts_code == "002153.SZ")
    assert shiji.holding.enable_amount == 2800
    assert [(order.order_type, order.price, order.shares, order.confirmed) for order in shiji.orders] == [
        ("sell_profit", Decimal("12.65"), 2800, False),
        ("sell_loss", Decimal("10.99"), 2800, False),
    ]
    assert all(order.order_type != "buy_limit" for order in shiji.orders)


def test_existing_draft_is_not_overwritten(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()

    first = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
        previous_order_path=None,
    )
    store.add_order(first.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    second = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
        previous_order_path=PREVIOUS_ORDER,
    )

    shiji = next(stock for stock in second.stocks if stock.ts_code == "002153.SZ")
    assert [order.order_type for order in shiji.orders] == ["buy_limit"]


def test_historical_draft_is_read_only_when_newer_date_exists(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()
    store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )
    imported.manage_date = "20260226"
    store.create_draft(
        imported,
        expected_trade_date="20260227",
        ptrade_json_path="/tmp/ptrade_data/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )

    assert store.load_draft("20260225").read_only is True
    assert store.load_draft("20260226").read_only is False


def test_order_confirmation_change_delete_and_restore(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )

    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    store.confirm_order(order_id)
    store.save_order_change(order_id, price=Decimal("11.5"), shares=1500, order_type="buy_limit")
    changed = next(
        order
        for stock in store.load_draft("20260225").stocks
        for order in stock.orders
        if order.id == order_id
    )
    assert changed.confirmed is False
    assert changed.price == Decimal("11.5")

    snapshot = store.delete_order(order_id)
    assert all(order.id != order_id for stock in store.load_draft("20260225").stocks for order in stock.orders)
    restored_id = store.restore_deleted_order(snapshot)
    assert restored_id != order_id
    assert any(order.id == restored_id for stock in store.load_draft("20260225").stocks for order in stock.orders)

