from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.trade_calendar import TradeCalendar


def test_trade_calendar_lookup(sqlite_conn):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)
    calendar.upsert_trade_calendar(
        [
            {"cal_date": "20260223", "is_open": 1},
            {"cal_date": "20260224", "is_open": 1},
            {"cal_date": "20260225", "is_open": 1},
            {"cal_date": "20260226", "is_open": 1},
            {"cal_date": "20260227", "is_open": 1},
            {"cal_date": "20260228", "is_open": 0},
        ],
        updated_on="20260609",
    )

    assert calendar.is_trade_day("20260225") is True
    assert calendar.is_trade_day("20260228") is False
    assert calendar.previous_trade_day("20260225") == "20260224"
    assert calendar.previous_trade_day("20260223") is None
    assert calendar.next_trade_day("20260225") == "20260226"
    assert calendar.next_trade_day("20260228") is None


def test_sync_trade_calendar_from_tushare(sqlite_conn):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)

    class FakePro:
        def query(self, api_name, start_date, end_date, fields):
            assert api_name == "trade_cal"
            assert start_date == "20260101"
            assert end_date == "20271231"
            assert fields == "cal_date,is_open"
            return [
                {"cal_date": "20260609", "is_open": 1},
                {"cal_date": "20260610", "is_open": 0},
            ]

    count = calendar.sync_from_tushare("token", today="20260609", pro_client=FakePro())

    assert count == 2
    assert calendar.has_calendar_for("20260609") is True
    assert calendar.is_trade_day("20260609") is True
    assert calendar.is_trade_day("20260610") is False


def test_sync_trade_calendar_range_from_tushare(sqlite_conn):
    initialize_schema(sqlite_conn)
    calendar = TradeCalendar(sqlite_conn)

    class FakePro:
        def query(self, api_name, start_date, end_date, fields):
            assert api_name == "trade_cal"
            assert start_date == "20260225"
            assert end_date == "20260610"
            assert fields == "cal_date,is_open"
            return [
                {"cal_date": "20260225", "is_open": 1},
                {"cal_date": "20260226", "is_open": 1},
                {"cal_date": "20260610", "is_open": 1},
            ]

    count = calendar.sync_range_from_tushare(
        "token",
        start_date="20260225",
        end_date="20260610",
        pro_client=FakePro(),
    )

    assert count == 3
    assert calendar.trade_days_between("20260225", "20260610") == ["20260225", "20260226", "20260610"]
    assert calendar.latest_trade_day_on_or_before("20260610") == "20260610"
