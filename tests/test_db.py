from ptrade_order_tool.data.db import initialize_schema


def test_initialize_schema_creates_expected_tables(sqlite_conn):
    initialize_schema(sqlite_conn)

    rows = sqlite_conn.execute(
        "select name from sqlite_master where type = 'table'"
    ).fetchall()
    names = {row["name"] for row in rows}

    assert {
        "app_meta",
        "stock_basic",
        "trade_calendar",
        "sessions",
        "fund_snapshots",
        "holdings",
        "draft_stocks",
        "orders",
        "daily_quotes",
    } <= names
