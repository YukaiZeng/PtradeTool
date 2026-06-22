from datetime import datetime
from decimal import Decimal
from ptrade_order_tool.app_service import AppService, find_latest_ptrade_json
from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
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

    result = service.open_latest_on_startup(now=datetime(2026, 2, 25, 17, 31))

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
    first = service.open_latest_on_startup(now=datetime(2026, 2, 25, 17, 31)).draft
    order_id = service.drafts.add_order(first.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)

    second = service.open_latest_on_startup(now=datetime(2026, 2, 25, 17, 31)).draft

    assert any(order.id == order_id for stock in second.stocks for order in stock.orders)


def test_open_latest_on_startup_replaces_blank_same_date_draft(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )
    service.open_blank_manage_date("20260225")
    latest = ptrade_dir / "20260225.json"
    latest.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    draft = service.open_latest_on_startup(now=datetime(2026, 2, 25, 17, 31)).draft

    assert draft is not None
    assert draft.ptrade_json_path == str(latest)
    assert any(stock.is_holding for stock in draft.stocks)


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


def test_import_ptrade_json_replaces_blank_same_date_draft(sqlite_conn, tmp_path):
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
    blank = service.open_blank_manage_date("20260225")
    assert blank.stocks == []

    draft = service.import_ptrade_json(manual)

    assert draft.manage_date == "20260225"
    assert draft.ptrade_json_path == str(manual)
    assert any(stock.is_holding for stock in draft.stocks)
    assert any(stock.ts_code == "002153.SZ" for stock in draft.stocks)


def test_import_ptrade_json_does_not_overwrite_edited_blank_draft(sqlite_conn, tmp_path):
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
    service.open_blank_manage_date("20260225")
    service.add_manual_stock_by_code("20260225", "600000.SH", stock_name="浦发银行")

    try:
        service.import_ptrade_json(manual)
    except ValueError as exc:
        assert "已有手动草稿" in str(exc)
    else:
        raise AssertionError("edited blank draft should not be overwritten")

    draft = service.load_draft("20260225")
    assert [stock.ts_code for stock in draft.stocks] == ["600000.SH"]


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
    draft = service.open_latest_on_startup(now=datetime(2026, 2, 25, 17, 31)).draft
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", 11.4, 1400)

    reimported = service.reimport_current_draft("20260225")

    assert reimported.ptrade_json_path == str(manual)
    assert all(not stock.orders for stock in reimported.stocks)

def test_open_latest_on_startup_handles_missing_directory(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    calendar = setup_calendar(sqlite_conn)
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(tmp_path / "missing"), order_data_dir=str(tmp_path / "order_data")),
        FakeStockMatcher(),
        calendar,
    )

    result = service.open_latest_on_startup(today="20260225", now=datetime(2026, 2, 25, 17, 31))

    assert result.draft is not None
    assert result.draft.manage_date == "20260225"
    assert "空白交易单" in result.message


def test_open_latest_on_startup_creates_blank_editable_draft_without_ptrade_json(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260609", "is_open": 1},
            {"cal_date": "20260610", "is_open": 1},
            {"cal_date": "20260611", "is_open": 1},
        ],
        updated_on="20260610",
    )
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir="", order_data_dir=str(tmp_path / "order_data")),
        FakeStockMatcher(),
        calendar,
    )

    result = service.open_latest_on_startup(today="20260610", now=datetime(2026, 6, 10, 17, 31))
    draft = result.draft

    assert draft is not None
    assert draft.manage_date == "20260610"
    assert draft.expected_trade_date == "20260611"
    assert draft.ptrade_json_path == ""
    assert draft.stocks == []
    assert draft.read_only is False
    assert "空白交易单" in result.message


def test_open_latest_on_startup_keeps_previous_trade_day_before_cutoff(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    (ptrade_dir / "20260225.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (ptrade_dir / "20260226.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    result = service.open_latest_on_startup(now=datetime(2026, 2, 26, 17, 29))

    assert result.draft is not None
    assert result.draft.manage_date == "20260225"
    assert result.draft.read_only is False


def test_open_latest_on_startup_switches_to_current_trade_day_after_cutoff(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    order_dir = tmp_path / "order_data"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    (ptrade_dir / "20260225.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (ptrade_dir / "20260226.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=str(order_dir)),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    result = service.open_latest_on_startup(now=datetime(2026, 2, 26, 17, 30, 1))

    assert result.draft is not None
    assert result.draft.manage_date == "20260226"
    assert result.draft.read_only is False


def test_cutoff_boundary_still_uses_previous_trade_day(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir="", order_data_dir=str(tmp_path / "order_data")),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
    )

    assert service.current_editable_manage_date(now=datetime(2026, 2, 26, 17, 30)) == "20260225"
    assert service.current_editable_manage_date(now=datetime(2026, 2, 26, 17, 30, 1)) == "20260226"


def test_previous_trade_day_stays_editable_before_cutoff_when_current_session_exists(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir="", order_data_dir=str(tmp_path / "order_data")),
        FakeStockMatcher(),
        setup_calendar(sqlite_conn),
        now_provider=lambda: datetime(2026, 2, 26, 17, 29),
    )
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    service.drafts.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path="/tmp/ptrade_data/20260225.json",
        export_json_path="/tmp/order_data/20260225.json",
    )
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/ptrade_data/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )

    assert service.load_draft("20260225").read_only is False
    assert service.empty_manage_date_view("20260224").read_only is True
    assert service.load_draft("20260226").read_only is False


def test_list_manage_dates_uses_calendar_range_when_no_ptrade_json(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260608", "is_open": 1},
            {"cal_date": "20260609", "is_open": 1},
            {"cal_date": "20260610", "is_open": 1},
        ],
        updated_on="20260610",
    )
    service = AppService(sqlite_conn, AppConfig(), FakeStockMatcher(), calendar)

    assert service.list_manage_dates(today="20260610", now=datetime(2026, 6, 10, 17, 31)) == ["20260610", "20260609"]


def test_list_manage_dates_includes_continuous_trade_days_from_previous_trade_day(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    ptrade_dir.mkdir()
    (ptrade_dir / "20260616.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260612", "is_open": 1},
            {"cal_date": "20260613", "is_open": 0},
            {"cal_date": "20260614", "is_open": 0},
            {"cal_date": "20260615", "is_open": 1},
            {"cal_date": "20260616", "is_open": 1},
        ],
        updated_on="20260616",
    )
    service = AppService(sqlite_conn, AppConfig(ptrade_data_dir=str(ptrade_dir)), FakeStockMatcher(), calendar)

    assert service.list_manage_dates(today="20260616", now=datetime(2026, 6, 16, 17, 31)) == ["20260616", "20260615"]


def test_maintain_trade_calendar_starts_from_earliest_ptrade_json(sqlite_conn, tmp_path, monkeypatch):
    initialize_schema(sqlite_conn)
    ptrade_dir = tmp_path / "ptrade_data"
    ptrade_dir.mkdir()
    (ptrade_dir / "20260225.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("TUSHARE_TOKEN=abc\n", encoding="utf-8")
    calendar = TradeCalendar(sqlite_conn)
    captured = {}

    class FakePro:
        def query(self, api_name, start_date, end_date, fields):
            captured.update(api_name=api_name, start_date=start_date, end_date=end_date, fields=fields)
            return [
                {"cal_date": "20260224", "is_open": 1},
                {"cal_date": "20260225", "is_open": 1},
                {"cal_date": "20260610", "is_open": 1},
            ]

    service = AppService(
        sqlite_conn,
        AppConfig(ptrade_data_dir=str(ptrade_dir), order_data_dir=""),
        FakeStockMatcher(),
        calendar,
    )

    count = service.maintain_trade_calendar(
        today="20260610",
        executable_dir=tmp_path,
        user_data_dir=tmp_path / "user",
        pro_client=FakePro(),
    )

    assert count == 3
    assert captured["start_date"] == "20260111"
    assert captured["end_date"] >= "20260610"
    assert service.list_manage_dates(today="20260610", now=datetime(2026, 6, 10, 17, 31)) == ["20260610", "20260225", "20260224"]
