from datetime import datetime
from decimal import Decimal

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
