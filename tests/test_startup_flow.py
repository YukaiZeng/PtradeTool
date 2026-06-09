from decimal import Decimal

from ptrade_order_tool.app_service import AppService, find_latest_ptrade_json
from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.trade_calendar import TradeCalendar
from tests.test_ptrade_importer import FIXTURE, FakeStockMatcher


def setup_calendar(sqlite_conn):
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260224", "is_open": 1},
            {"cal_date": "20260225", "is_open": 1},
            {"cal_date": "20260226", "is_open": 1},
        ],
        updated_on="20260609",
    )
    return calendar


def test_find_latest_ptrade_json_ignores_invalid_names(tmp_path):
    (tmp_path / "20260224.json").write_text("{}", encoding="utf-8")
    (tmp_path / "20260225.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ptrade_20260226.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")

    assert find_latest_ptrade_json(str(tmp_path)).name == "20260225.json"


def test_open_latest_on_startup_creates_draft(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    latest = ptrade_dir / "20260225.json"
    latest.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    result = service.open_latest_on_startup()

    assert result.draft is not None
    assert result.draft.manage_date == "20260225"
    assert result.draft.expected_trade_date == "20260226"
    assert result.draft.fund.calibrated_cash == Decimal("33361.86")


def test_open_latest_on_startup_does_not_overwrite_existing_draft(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    latest = ptrade_dir / "20260225.json"
    latest.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )
    first = service.open_latest_on_startup().draft
    order_id = service.drafts.add_order(first.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    second = service.open_latest_on_startup().draft

    assert any(order.id == order_id for stock in second.stocks for order in stock.orders)


def test_reimport_manage_date_overwrites_existing_draft(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    latest = ptrade_dir / "20260225.json"
    latest.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )
    first = service.open_latest_on_startup().draft
    service.drafts.add_order(first.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    reimported = service.reimport_manage_date(latest)

    shiji = next(stock for stock in reimported.stocks if stock.ts_code == "002153.SZ")
    assert shiji.orders == []


def test_import_ptrade_json_opens_manual_file(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    manual = ptrade_dir / "20260225.json"
    manual.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir="", order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    draft = service.import_ptrade_json(manual)

    assert draft.manage_date == "20260225"
    assert draft.ptrade_json_path == str(manual)


def test_reimport_current_draft_uses_original_ptrade_json(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    manual = ptrade_dir / "20260225.json"
    manual.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )
    draft = service.open_latest_on_startup().draft
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", 11.4, 1400)

    reimported = service.reimport_current_draft("20260225")

    assert reimported.ptrade_json_path == str(manual)
    assert all(not stock.orders for stock in reimported.stocks)

def test_open_latest_on_startup_handles_missing_directory(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(tmp_path / "missing"), order_data_dir=str(tmp_path / "order_data")),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    result = service.open_latest_on_startup()

    assert result.draft is None
    assert "未找到" in result.message
