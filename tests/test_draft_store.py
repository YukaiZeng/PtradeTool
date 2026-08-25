from decimal import Decimal
from pathlib import Path

import pytest

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
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=PREVIOUS_ORDER,
    )

    shiji = next(stock for stock in draft.stocks if stock.ts_code == "002153.SZ")
    assert shiji.holding.enable_amount == 2800
    assert [(order.order_type, order.price, order.shares, order.confirmed) for order in shiji.orders] == [
        ("sell_profit", Decimal("12.65"), 2800, False),
        ("sell_loss", Decimal("10.99"), 2800, False),
    ]
    assert all(order.order_type != "buy_limit" for order in shiji.orders)


def test_inherited_sell_orders_keep_previous_order_shares(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"300251.SZ": {"sell_profit": [{"price": 12.65, "shares": 100}], "sell_loss": [{"price": 10.99, "shares": 100}]}}',
        encoding="utf-8",
    )

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )

    guangxian = next(stock for stock in draft.stocks if stock.ts_code == "300251.SZ")
    assert guangxian.holding.current_amount == 200
    assert guangxian.holding.enable_amount == 0
    assert [(order.price, order.shares) for order in guangxian.orders] == [
        (Decimal("12.65"), 100),
        (Decimal("10.99"), 100),
    ]


def test_create_draft_does_not_inherit_sell_orders_for_zero_current_amount(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()
    zero_holding = next(holding for holding in imported.holdings if holding.ts_code == "002153.SZ")
    zero_holding.current_amount = 0
    zero_holding.enable_amount = 0
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"002153.SZ": {"sell_profit": [{"price": 12.65, "shares": 2800}], "sell_loss": [{"price": 10.99, "shares": 2800}]}}',
        encoding="utf-8",
    )

    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )

    assert "002153.SZ" not in {stock.ts_code for stock in draft.stocks}
    assert sqlite_conn.execute(
        "select count(*) from orders where manage_date = ? and ts_code = ?",
        (draft.manage_date, "002153.SZ"),
    ).fetchone()[0] == 0


def test_sync_fund_and_holdings_removes_inherited_sell_orders_for_closed_positions(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"002153.SZ": {"sell_profit": [{"price": 12.65, "shares": 2800}]}}',
        encoding="utf-8",
    )
    store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )
    imported = create_imported()
    zero_holding = next(holding for holding in imported.holdings if holding.ts_code == "002153.SZ")
    zero_holding.current_amount = 0
    zero_holding.enable_amount = 0

    store.sync_fund_and_holdings(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )

    draft = store.load_draft("20260225")
    assert "002153.SZ" not in {stock.ts_code for stock in draft.stocks}
    assert sqlite_conn.execute(
        "select count(*) from orders where manage_date = ? and ts_code = ?",
        (draft.manage_date, "002153.SZ"),
    ).fetchone()[0] == 0


def test_load_draft_hides_legacy_inherited_sell_orders_for_zero_current_amount(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"002153.SZ": {"sell_loss": [{"price": 10.99, "shares": 2800}]}}',
        encoding="utf-8",
    )
    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )
    sqlite_conn.execute(
        "update holdings set current_amount = 0, enable_amount = 0 where manage_date = ? and ts_code = ?",
        (draft.manage_date, "002153.SZ"),
    )
    sqlite_conn.commit()

    reloaded = store.load_draft(draft.manage_date)

    assert "002153.SZ" not in {stock.ts_code for stock in reloaded.stocks}


def test_inherited_sell_orders_stop_at_nearest_effective_stock_day(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    newer_order_path = tmp_path / "order_20260225.json"
    newer_order_path.write_text(
        '{"002153.SZ": {"sell_profit": [{"price": 12.65, "shares": 2800}]}}',
        encoding="utf-8",
    )
    older_order_path = tmp_path / "order_20260224.json"
    older_order_path.write_text(
        '{"002153.SZ": {"sell_loss": [{"price": 10.99, "shares": 2800}]}}',
        encoding="utf-8",
    )

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=[newer_order_path, older_order_path],
    )

    shiji = next(stock for stock in draft.stocks if stock.ts_code == "002153.SZ")
    assert [(order.order_type, order.price, order.shares) for order in shiji.orders] == [
        ("sell_profit", Decimal("12.65"), 2800),
    ]


def test_create_draft_inherits_unfilled_previous_day_pullback_plan(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        (
            '{"600000.SH": {"stock_name": "浦发银行", '
            '"buy_limit": [{"price": 9.50, "shares": 1000}], '
            '"sell_profit": [{"price": 10.50, "shares": 1000}], '
            '"sell_loss": [{"price": 9.00, "shares": 1000}]}}'
        ),
        encoding="utf-8",
    )

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_pullback_order_path=previous_order_path,
    )

    pullback_stock = next(stock for stock in draft.stocks if stock.ts_code == "600000.SH")
    assert pullback_stock.stock_name == "浦发银行"
    assert pullback_stock.is_holding is False
    assert [(order.order_type, order.price, order.shares, order.confirmed, order.source) for order in pullback_stock.orders] == [
        ("buy_limit", Decimal("9.50"), 1000, False, "inherited"),
        ("sell_profit", Decimal("10.50"), 1000, False, "inherited"),
        ("sell_loss", Decimal("9.00"), 1000, False, "inherited"),
    ]


def test_create_draft_ignores_malformed_previous_order_json(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text("{broken", encoding="utf-8")

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )

    assert draft.manage_date == "20260225"
    assert sum(len(stock.orders) for stock in draft.stocks) == 0


def test_create_draft_ignores_malformed_previous_order_items(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"002153.SZ": {"sell_profit": [{"price": 12.5}, "bad"], "sell_loss": {"price": 9.9}}}',
        encoding="utf-8",
    )

    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=previous_order_path,
    )

    assert draft.manage_date == "20260225"
    assert sum(len(stock.orders) for stock in draft.stocks) == 0


def test_existing_draft_is_not_overwritten(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()

    first = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=None,
    )
    store.add_order(first.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    second = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=PREVIOUS_ORDER,
    )

    shiji = next(stock for stock in second.stocks if stock.ts_code == "002153.SZ")
    assert [order.order_type for order in shiji.orders] == ["buy_limit"]


def test_load_draft_recomputes_next_trade_available_cash_from_totals(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )
    sqlite_conn.execute(
        "update fund_snapshots set calibrated_cash = ? where manage_date = ?",
        ("1", "20260225"),
    )
    sqlite_conn.commit()

    draft = store.load_draft("20260225")

    assert draft.fund.next_trade_available_cash == Decimal("33361.86")


def test_overwrite_draft_rolls_back_when_inherited_order_is_invalid(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()
    original = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
        previous_order_path=None,
    )
    order_id = store.add_order(original.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    previous_order_path = tmp_path / "order_20260224.json"
    previous_order_path.write_text(
        '{"002153.SZ": {"sell_profit": [{"price": "bad", "shares": 2800}]}}',
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        store.create_draft(
            imported,
            expected_trade_date="20260226",
            ptrade_json_path=str(PTRADER_FIXTURE),
            export_json_path="/tmp/order_data/order_20260225.json",
            previous_order_path=previous_order_path,
            overwrite=True,
        )

    draft = store.load_draft("20260225")
    assert any(order.id == order_id for stock in draft.stocks for order in stock.orders)


def test_historical_draft_is_read_only_when_newer_date_exists(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = create_imported()
    store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )
    imported.manage_date = "20260226"
    store.create_draft(
        imported,
        expected_trade_date="20260227",
        ptrade_json_path="/tmp/ptrade_data/ptrade_20260226.json",
        export_json_path="/tmp/order_data/order_20260226.json",
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
        export_json_path="/tmp/order_data/order_20260225.json",
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


def test_exported_draft_stays_modified_after_multiple_edits(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    store.confirm_order(order_id)
    store.mark_exported(draft.manage_date)

    store.save_order_change(order_id, price=Decimal("11.5"), shares=1500, order_type="buy_limit")
    assert store.load_draft(draft.manage_date).export_state == "modified_after_export"

    store.confirm_order(order_id)
    assert store.load_draft(draft.manage_date).export_state == "modified_after_export"


def test_save_and_confirm_order_updates_values_and_confirmation_together(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    store.save_and_confirm_order(order_id, price=Decimal("11.5"), shares=1500, order_type="buy_limit")

    order = next(
        order
        for stock in store.load_draft(draft.manage_date).stocks
        for order in stock.orders
        if order.id == order_id
    )
    assert order.price == Decimal("11.5")
    assert order.shares == 1500
    assert order.confirmed is True


def test_decimal_values_are_persisted_without_float_rounding(sqlite_conn):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        create_imported(),
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/order_20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("0.29"), 100)

    row = sqlite_conn.execute("select price from orders where id = ?", (order_id,)).fetchone()
    loaded_order = next(
        order
        for stock in store.load_draft("20260225").stocks
        for order in stock.orders
        if order.id == order_id
    )

    assert row["price"] == "0.29"
    assert loaded_order.price == Decimal("0.29")
