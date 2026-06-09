from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.stock_master import StockMaster
from ptrade_order_tool.data.trade_calendar import TradeCalendar


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
    assert stock_master.resolve_stock("600000")["name"] == "浦发银行"
