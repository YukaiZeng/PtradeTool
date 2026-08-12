import json
from datetime import datetime
from decimal import Decimal

import pytest

from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from ptrade_order_tool.data.trade_calendar import TradeCalendar
from tests.test_ptrade_importer import FIXTURE, FakeStockMatcher


def make_service(sqlite_conn, tmp_path, *, now_provider=None):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    (ptrade_dir / "20260225.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260224", "is_open": 1},
            {"cal_date": "20260225", "is_open": 1},
            {"cal_date": "20260226", "is_open": 1},
        ],
        updated_on="20260609",
    )
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        calendar,
        now_provider=now_provider or (lambda: datetime(2026, 2, 25, 17, 31)),
    )
    draft = service.open_latest_on_startup().draft
    return service, draft, order_dir


def test_update_and_confirm_order(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    updated = service.update_and_confirm_order(
        order_id,
        price=Decimal("11.5"),
        shares=1500,
        order_type="buy_limit",
    )

    order = next(order for stock in updated.stocks for order in stock.orders if order.id == order_id)
    assert order.confirmed is True
    assert order.price == Decimal("11.5")
    assert order.shares == 1500


def test_export_validation_blocks_buy_price_conflicting_with_cached_close(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.40"), 100)
    service.update_and_confirm_order(order_id, price=Decimal("11.40"), shares=100, order_type="buy_limit")
    service.cache_daily_quote_rows(
        draft.manage_date,
        [{
            "ts_code": "002153.SZ",
            "trade_date": draft.manage_date,
            "open": "11.00",
            "high": "11.00",
            "low": "11.00",
            "close": "11.00",
            "pre_close": "11.00",
            "change": "0",
            "pct_chg": "0",
            "vol": "0",
            "amount": "0",
        }],
    )

    validation = service.validate_draft_for_export(draft.manage_date)

    assert validation.can_export is False
    assert "002153.SZ 石基信息 回调买价格 11.40 不小于收盘价 11.00（阻断）" in validation.blockers


def test_delete_order(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    updated = service.delete_order(order_id)

    assert all(order.id != order_id for stock in updated.stocks for order in stock.orders)


def test_add_order(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    updated = service.add_order(
        draft.manage_date,
        ts_code="002153.SZ",
        stock_name="石基信息",
        order_type="buy_limit",
    )

    order = next(order for stock in updated.stocks for order in stock.orders if order.order_type == "buy_limit")
    assert order.price == Decimal("0")
    assert order.shares == 0
    assert order.confirmed is False


def test_add_manual_stock(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    updated = service.add_manual_stock(draft.manage_date, "600000")

    stock = next(stock for stock in updated.stocks if stock.ts_code == "600000.SH")
    assert stock.stock_name == "浦发银行"
    assert stock.is_holding is False
    assert stock.orders == []


def test_add_manual_stock_uses_search_when_available(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher(FakeStockMatcher):
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            assert query == "pfyh"
            return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]

    service.stock_matcher = SearchMatcher()
    updated = service.add_manual_stock(draft.manage_date, "pfyh")

    assert any(stock.ts_code == "600000.SH" for stock in updated.stocks)


def test_add_manual_stock_by_code_accepts_selected_candidate(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchOnlyMatcher:
        def resolve_stock(self, query: str):
            return None

    service.stock_matcher = SearchOnlyMatcher()

    updated = service.add_manual_stock_by_code(draft.manage_date, "600000.SH", stock_name="浦发银行")

    assert any(stock.ts_code == "600000.SH" and stock.stock_name == "浦发银行" for stock in updated.stocks)


def test_load_daily_quotes_syncs_missing_trade_date(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class FakeDailyClient:
        def query(self, api_name, fields="", **kwargs):
            assert api_name == "daily"
            assert kwargs == {"trade_date": "20260225"}
            assert "ts_code" in fields
            return [
                {
                    "ts_code": "002153.SZ",
                    "trade_date": "20260225",
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.5,
                    "close": 11.0,
                    "pre_close": 10.0,
                    "change": 1.0,
                    "pct_chg": 10.0,
                    "vol": 10000,
                    "amount": 250000,
                }
            ]

    quotes = service.load_daily_quotes(
        draft.manage_date,
        token="token",
        pro_client=FakeDailyClient(),
        ts_codes=["002153.SZ"],
    )

    assert quotes["002153.SZ"].close == Decimal("11.0")
    assert quotes["002153.SZ"].pct_chg == Decimal("10.0")
    assert quotes["002153.SZ"].amount == Decimal("250000")


def test_load_daily_quotes_silently_returns_cache_or_empty_on_sync_failure(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class FailingClient:
        def query(self, *args, **kwargs):
            raise RuntimeError("权限不足")

    assert service.load_daily_quotes(draft.manage_date, token="token", pro_client=FailingClient()) == {}


def test_daily_quote_no_data_is_temporarily_suppressed_but_request_failure_is_not(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    service.cache_daily_quote_fetch_result(
        draft.manage_date,
        requested_ts_codes=["002153.SZ", "600000.SH"],
        rows=[],
        successful_ts_codes=["002153.SZ"],
    )

    assert service.daily_quote_ts_codes_to_fetch(draft.manage_date, ["002153.SZ", "600000.SH"]) == ["600000.SH"]


def test_json_sync_rolls_back_ptrade_changes_when_order_replacement_fails(sqlite_conn, tmp_path, monkeypatch):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    ptrade_path = tmp_path / "ptrade_data" / "20260225.json"
    original_cash = sqlite_conn.execute(
        "select cash from fund_snapshots where manage_date = ?", (draft.manage_date,)
    ).fetchone()["cash"]
    (order_dir / "20260225.json").write_text("{}", encoding="utf-8")
    original_replace_orders = service.drafts.replace_orders

    def fail_after_order_replace(*args, **kwargs):
        original_replace_orders(*args, **kwargs)
        raise RuntimeError("order replacement failed")

    monkeypatch.setattr(service.drafts, "replace_orders", fail_after_order_replace)

    with pytest.raises(RuntimeError, match="order replacement failed"):
        service.sync_json_to_draft(draft.manage_date)

    assert ptrade_path.exists()
    assert sqlite_conn.execute(
        "select cash from fund_snapshots where manage_date = ?", (draft.manage_date,)
    ).fetchone()["cash"] == original_cash


def test_delete_with_snapshot_and_restore(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    updated, snapshot = service.delete_order_with_snapshot(order_id)
    assert all(order.id != order_id for stock in updated.stocks for order in stock.orders)

    restored = service.restore_deleted_order(snapshot)
    assert any(order.order_type == "buy_limit" for stock in restored.stocks for order in stock.orders)


def test_delete_manage_date_removes_historical_draft(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.add_manual_stock_by_code(draft.manage_date, "600000.SH", stock_name="浦发银行")

    service.delete_manage_date(draft.manage_date)

    assert service.drafts.list_manage_dates() == []
    assert "20260225" in service.list_manage_dates(today="20260226")
    assert sqlite_conn.execute("select count(*) as count from draft_stocks where manage_date = ?", (draft.manage_date,)).fetchone()["count"] == 0


def test_export_draft_writes_file_and_marks_exported(sqlite_conn, tmp_path):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")

    validation = service.export_draft("20260225")

    assert validation.can_export is True
    assert (order_dir / "20260225.json").exists()
    assert service.load_draft("20260225").export_state == "exported"


def test_export_draft_uses_current_editable_manage_date_for_read_only_state(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path, now_provider=lambda: datetime(2026, 2, 26, 17, 29))
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")

    validation = service.export_draft("20260225")

    assert validation.can_export is True
    assert service.load_draft("20260225").read_only is False


def test_json_sync_plan_ignores_ptrade_order_field_when_fund_and_hold_match(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    plan = service.json_sync_plan(draft.manage_date)

    assert plan.ptrade_json_path is not None
    assert plan.has_ptrade_changes is False
    assert plan.has_order_changes is False
    assert plan.can_sync is False


def test_sync_json_to_draft_replaces_orders_from_export_json(sqlite_conn, tmp_path):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    stale_id = service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    service.update_and_confirm_order(stale_id, price=Decimal("8.8"), shares=1000, order_type="buy_limit")
    order_path = order_dir / "20260225.json"
    order_path.write_text(
        json.dumps(
            {
                "002153.SZ": {
                    "stock_name": "石基信息",
                    "buy_limit": [{"price": 11.4, "shares": 1400}],
                    "sell_profit": [{"price": 12.65, "shares": 2800}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = service.json_sync_plan("20260225")
    synced = service.sync_json_to_draft("20260225")

    assert plan.has_order_changes is True
    shiji = next(stock for stock in synced.stocks if stock.ts_code == "002153.SZ")
    assert [(order.order_type, order.price, order.shares, order.confirmed) for order in shiji.orders] == [
        ("buy_limit", Decimal("11.4"), 1400, True),
        ("sell_profit", Decimal("12.65"), 2800, True),
    ]
    assert synced.export_state == "exported"
    leiman = next(stock for stock in synced.stocks if stock.ts_code == "300162.SZ")
    assert leiman.orders == []
    assert service.json_sync_plan("20260225").can_sync is False


def test_sync_json_to_draft_clears_orders_for_empty_export_json(sqlite_conn, tmp_path):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    (order_dir / "20260225.json").write_text("{}", encoding="utf-8")

    synced = service.sync_json_to_draft("20260225")

    assert all(not stock.orders for stock in synced.stocks)


def test_sync_json_to_draft_updates_fund_and_hold_from_ptrade_json(sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    ptrade_path = tmp_path / "ptrade_data" / "20260225.json"
    data = json.loads(ptrade_path.read_text(encoding="utf-8"))
    data["Fund"]["cash"] = 1000
    data["Hold"]["002153.SZ"]["last_price"] = 12.34
    data["Hold"]["002153.SZ"]["market_value"] = 34552
    ptrade_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    plan = service.json_sync_plan(draft.manage_date)
    synced = service.sync_json_to_draft(draft.manage_date)

    assert plan.has_ptrade_changes is True
    assert synced.fund.cash == Decimal("1000")
    shiji = next(stock for stock in synced.stocks if stock.ts_code == "002153.SZ")
    assert shiji.holding.last_price == Decimal("12.34")
    assert shiji.holding.market_value == Decimal("34552")


def test_sync_json_to_draft_can_update_historical_manage_date(sqlite_conn, tmp_path):
    service, _, order_dir = make_service(sqlite_conn, tmp_path, now_provider=lambda: datetime(2026, 2, 26, 17, 31))
    draft = service.import_ptrade_json(tmp_path / "ptrade_data" / "20260225.json")
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    (order_dir / "20260225.json").write_text(
        json.dumps({"600000.SH": {"stock_name": "浦发银行", "buy_stop": [{"price": 10, "shares": 1000}]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    synced = service.sync_json_to_draft(draft.manage_date)

    assert synced.read_only is True
    pufa = next(stock for stock in synced.stocks if stock.ts_code == "600000.SH")
    assert pufa.orders[0].confirmed is True


def test_service_rejects_interactive_changes_to_historical_draft(sqlite_conn, tmp_path):
    service, _, _ = make_service(sqlite_conn, tmp_path, now_provider=lambda: datetime(2026, 2, 26, 17, 31))
    draft = service.import_ptrade_json(tmp_path / "ptrade_data" / "20260225.json")
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "test", "buy_limit", Decimal("11.4"), 1400)

    with pytest.raises(PermissionError):
        service.update_order_change(
            order_id,
            price=Decimal("11.5"),
            shares=1400,
            order_type="buy_limit",
        )
