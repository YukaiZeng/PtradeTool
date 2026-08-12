from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.stock_master import StockMaster
from ptrade_order_tool.data.trade_calendar import TradeCalendar
from ptrade_order_tool.ui.main_window import MainWindow, StockUpdateWorker


class FakePro:
    def query(self, api_name, **kwargs):
        if api_name == "trade_cal":
            return [{"cal_date": "20260609", "is_open": 1}]
        if api_name == "stock_basic":
            assert kwargs["fields"] == "ts_code,symbol,name,list_status"
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行", "list_status": "L"}
            ]
        raise AssertionError(api_name)


def make_service(sqlite_conn):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar([{"cal_date": "20260609", "is_open": 1}], updated_on="20260609")
    stock_master = StockMaster(sqlite_conn)
    return AppService(sqlite_conn, AppConfig(), stock_master, calendar), stock_master


def test_update_stock_basic_from_env_file(sqlite_conn, tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    (tmp_path / ".env").write_text("TUSHARE_TOKEN=abc\n", encoding="utf-8")
    service, stock_master = make_service(sqlite_conn)

    count = service.update_stock_basic(
        today="20260609",
        executable_dir=tmp_path / "exe",
        user_data_dir=tmp_path,
        pro_client=FakePro(),
    )

    assert count == 1
    assert stock_master.resolve_stock("600000")["name"] == "浦发银行"
    assert service.stock_update_button_state("20260609") == "updated_disabled"


def test_update_stock_basic_syncs_missing_calendar_first(sqlite_conn, tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    (tmp_path / ".env").write_text("TUSHARE_TOKEN=abc\n", encoding="utf-8")
    initialize_schema(sqlite_conn)
    stock_master = StockMaster(sqlite_conn)
    service = AppService(sqlite_conn, AppConfig(), stock_master, TradeCalendar(sqlite_conn))

    count = service.update_stock_basic(
        today="20260609",
        executable_dir=tmp_path / "exe",
        user_data_dir=tmp_path,
        pro_client=FakePro(),
    )

    assert count == 1
    assert service.calendar.has_calendar_for("20260609") is True


def test_stock_update_worker_prepares_stock_rows_outside_ui_thread(monkeypatch):
    def query(_self, api_name, **_kwargs):
        if api_name == "trade_cal":
            return [{"cal_date": "20260609", "is_open": 1}]
        return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行", "list_status": "L"}]

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.TushareProClient.query", query)
    worker = StockUpdateWorker("token", "20260609", "20260101", "20271231")
    captured = []
    worker.finishedWithRows.connect(lambda today, calendar_rows, stock_rows: captured.append((today, calendar_rows, stock_rows)))

    worker.run()

    assert captured[0][0] == "20260609"
    assert captured[0][2][0] == ("600000.SH", "600000", "浦发银行", "pufayinhang", "pfyh", "L", "20260609")


def test_stock_update_worker_uses_default_timeout_for_full_stock_basic_response(monkeypatch):
    created_timeouts = []

    class FakeClient:
        def __init__(self, _token, timeout=30):
            created_timeouts.append(timeout)

        def query(self, api_name, **_kwargs):
            if api_name == "trade_cal":
                return []
            return []

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.TushareProClient", FakeClient)
    worker = StockUpdateWorker("token", "20260609", "20260101", "20271231")

    worker.run()

    assert created_timeouts == [30]


def test_stock_update_worker_skips_trade_calendar_when_already_synced(monkeypatch):
    queried = []

    class FakeClient:
        def __init__(self, _token, timeout=30):
            pass

        def query(self, api_name, **_kwargs):
            queried.append(api_name)
            if api_name == "stock_basic":
                return []
            raise AssertionError("trade_cal should not be queried")

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.TushareProClient", FakeClient)
    worker = StockUpdateWorker("token", "20260609", "20260101", "20271231", fetch_calendar=False)

    worker.run()

    assert queried == ["stock_basic"]


def test_stock_update_worker_emits_calendar_rows_even_when_stock_basic_fails(monkeypatch):
    class FakeClient:
        def __init__(self, _token, timeout=30):
            pass

        def query(self, api_name, **_kwargs):
            if api_name == "trade_cal":
                return [{"cal_date": "20260609", "is_open": 1}]
            raise RuntimeError("stock_basic unavailable")

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.TushareProClient", FakeClient)
    worker = StockUpdateWorker("token", "20260609", "20260101", "20271231")
    calendars = []
    worker.calendarRowsLoaded.connect(lambda today, rows: calendars.append((today, rows)))

    worker.run()

    assert calendars == [("20260609", [{"cal_date": "20260609", "is_open": 1}])]


def test_stock_update_result_uses_worker_date_for_persistence():
    captured = []

    class FakeService:
        def apply_stock_basic_update(self, **kwargs):
            captured.append(kwargs)
            return 1

    class Window:
        service = FakeService()

        def _handle_stock_update_finished(self, count):
            assert count == 1

    MainWindow._handle_stock_update_rows_loaded(Window(), "20260609", [], [("600000.SH", "600000", "浦发银行", "pufayinhang", "pfyh", "L", "20260609")])

    assert captured == [{
        "today": "20260609",
        "calendar_rows": [],
        "stock_rows": [("600000.SH", "600000", "浦发银行", "pufayinhang", "pfyh", "L", "20260609")],
    }]


def test_apply_stock_basic_update_persists_prepared_worker_rows(sqlite_conn):
    service, stock_master = make_service(sqlite_conn)

    count = service.apply_stock_basic_update(
        today="20260609",
        calendar_rows=[{"cal_date": "20260609", "is_open": 1}],
        stock_rows=[("600000.SH", "600000", "浦发银行", "pufayinhang", "pfyh", "L", "20260609")],
    )

    assert count == 1
    assert stock_master.resolve_stock("600000")["name"] == "浦发银行"
    assert stock_master.search_stocks("pfyh")[0]["ts_code"] == "600000.SH"
