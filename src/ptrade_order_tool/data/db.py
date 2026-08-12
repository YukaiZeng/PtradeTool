from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
create table if not exists app_meta (
    key text primary key,
    value text not null
);

create table if not exists stock_basic (
    ts_code text primary key,
    symbol text not null,
    name text not null,
    name_pinyin text not null,
    name_initials text not null,
    list_status text not null,
    updated_on text not null
);

create table if not exists trade_calendar (
    cal_date text primary key,
    is_open integer not null,
    updated_on text not null
);

create table if not exists sessions (
    manage_date text primary key,
    expected_trade_date text,
    ptrade_json_path text not null,
    export_json_path text not null,
    export_state text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists fund_snapshots (
    manage_date text primary key,
    cash text not null,
    positions_value text not null,
    portfolio_value text not null,
    stock_positions_value text not null,
    calibrated_cash text not null
);

create table if not exists holdings (
    manage_date text not null,
    ts_code text not null,
    stock_code text not null,
    stock_name text not null,
    current_amount integer not null,
    enable_amount integer not null,
    last_price text not null,
    cost_price text not null,
    market_value text not null,
    profit_ratio text not null,
    income_balance text not null,
    is_stock integer not null,
    primary key (manage_date, ts_code)
);

create table if not exists draft_stocks (
    manage_date text not null,
    ts_code text not null,
    stock_name text not null,
    created_at text not null,
    primary key (manage_date, ts_code)
);

create table if not exists orders (
    id integer primary key autoincrement,
    manage_date text not null,
    ts_code text not null,
    stock_name text not null,
    order_type text not null,
    price text not null,
    shares integer not null,
    confirmed integer not null,
    source text not null,
    warning text not null,
    sort_order integer not null
);

create table if not exists daily_quotes (
    trade_date text not null,
    ts_code text not null,
    open text not null,
    high text not null,
    low text not null,
    close text not null,
    pre_close text not null,
    change text not null,
    pct_chg text not null,
    vol text not null,
    amount text not null,
    updated_at text not null,
    primary key (trade_date, ts_code)
);

create table if not exists daily_quote_fetch_state (
    trade_date text not null,
    ts_code text not null,
    status text not null,
    next_retry_at text not null,
    updated_at text not null,
    primary key (trade_date, ts_code)
);
"""


DECIMAL_TEXT_COLUMNS = {
    "fund_snapshots": {"cash", "positions_value", "portfolio_value", "stock_positions_value", "calibrated_cash"},
    "holdings": {"last_price", "cost_price", "market_value", "profit_ratio", "income_balance"},
    "orders": {"price"},
    "daily_quotes": {"open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"},
}


MIGRATED_TABLE_SQL = {
    "fund_snapshots": """
        create table fund_snapshots__decimal_migration (
            manage_date text primary key,
            cash text not null,
            positions_value text not null,
            portfolio_value text not null,
            stock_positions_value text not null,
            calibrated_cash text not null
        )
    """,
    "holdings": """
        create table holdings__decimal_migration (
            manage_date text not null,
            ts_code text not null,
            stock_code text not null,
            stock_name text not null,
            current_amount integer not null,
            enable_amount integer not null,
            last_price text not null,
            cost_price text not null,
            market_value text not null,
            profit_ratio text not null,
            income_balance text not null,
            is_stock integer not null,
            primary key (manage_date, ts_code)
        )
    """,
    "orders": """
        create table orders__decimal_migration (
            id integer primary key autoincrement,
            manage_date text not null,
            ts_code text not null,
            stock_name text not null,
            order_type text not null,
            price text not null,
            shares integer not null,
            confirmed integer not null,
            source text not null,
            warning text not null,
            sort_order integer not null
        )
    """,
    "daily_quotes": """
        create table daily_quotes__decimal_migration (
            trade_date text not null,
            ts_code text not null,
            open text not null,
            high text not null,
            low text not null,
            close text not null,
            pre_close text not null,
            change text not null,
            pct_chg text not null,
            vol text not null,
            amount text not null,
            updated_at text not null,
            primary key (trade_date, ts_code)
        )
    """,
}


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute("begin immediate")
    try:
        _migrate_decimal_columns(conn)
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def _migrate_decimal_columns(conn: sqlite3.Connection) -> None:
    for table, decimal_columns in DECIMAL_TEXT_COLUMNS.items():
        rows = conn.execute(f"pragma table_info({table})").fetchall()
        if not rows:
            continue
        column_types = {_pragma_value(row, "name", 1): str(_pragma_value(row, "type", 2)).lower() for row in rows}
        if all(column_types.get(column) == "text" for column in decimal_columns):
            continue

        migration_table = f"{table}__decimal_migration"
        columns = [str(_pragma_value(row, "name", 1)) for row in rows]
        select_columns = [
            f"cast({column} as text)" if column in decimal_columns else column
            for column in columns
        ]
        conn.execute(f"drop table if exists {migration_table}")
        conn.execute(MIGRATED_TABLE_SQL[table])
        conn.execute(
            f"""
            insert into {migration_table} ({", ".join(columns)})
            select {", ".join(select_columns)}
            from {table}
            """
        )
        conn.execute(f"drop table {table}")
        conn.execute(f"alter table {migration_table} rename to {table}")


def _pragma_value(row: sqlite3.Row | tuple, key: str, index: int) -> object:
    try:
        return row[key]
    except (IndexError, TypeError):
        return row[index]
