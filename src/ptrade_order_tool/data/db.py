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
    cash real not null,
    positions_value real not null,
    portfolio_value real not null,
    stock_positions_value real not null,
    calibrated_cash real not null
);

create table if not exists holdings (
    manage_date text not null,
    ts_code text not null,
    stock_code text not null,
    stock_name text not null,
    current_amount integer not null,
    enable_amount integer not null,
    last_price real not null,
    cost_price real not null,
    market_value real not null,
    profit_ratio real not null,
    income_balance real not null,
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
    price real not null,
    shares integer not null,
    confirmed integer not null,
    source text not null,
    warning text not null,
    sort_order integer not null
);

create table if not exists daily_quotes (
    trade_date text not null,
    ts_code text not null,
    open real not null,
    high real not null,
    low real not null,
    close real not null,
    pre_close real not null,
    change real not null,
    pct_chg real not null,
    vol real not null,
    amount real not null,
    updated_at text not null,
    primary key (trade_date, ts_code)
);
"""


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
