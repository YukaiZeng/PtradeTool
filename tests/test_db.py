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
        "daily_quote_fetch_state",
    } <= names


def test_initialize_schema_migrates_decimal_columns_to_text(sqlite_conn):
    sqlite_conn.executescript(
        """
        create table sessions (
            manage_date text primary key,
            expected_trade_date text,
            ptrade_json_path text not null,
            export_json_path text not null,
            export_state text not null,
            created_at text not null,
            updated_at text not null
        );
        create table orders (
            id integer primary key autoincrement,
            manage_date text not null,
            ts_code text not null,
            stock_name text not null,
            order_type text not null,
            price real not null,
            shares integer not null,
            confirmed integer not null,
            source text not null,
            warning text not null,
            sort_order integer not null
        );
        insert into orders (
            manage_date, ts_code, stock_name, order_type, price,
            shares, confirmed, source, warning, sort_order
        ) values (
            '20260225', '002153.SZ', '石基信息', 'buy_limit', 0.29,
            100, 0, 'manual', '', 1
        );
        """
    )

    initialize_schema(sqlite_conn)

    table_info = sqlite_conn.execute("pragma table_info(orders)").fetchall()
    column_types = {row["name"]: row["type"].lower() for row in table_info}
    price = sqlite_conn.execute("select price from orders").fetchone()["price"]

    assert column_types["price"] == "text"
    assert price == "0.29"
