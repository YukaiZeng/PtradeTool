from __future__ import annotations

from pathlib import Path

from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import get_user_data_dir, load_config
from ptrade_order_tool.data.db import connect_db, initialize_schema
from ptrade_order_tool.data.stock_master import StockMaster
from ptrade_order_tool.data.trade_calendar import TradeCalendar


def create_app_service(user_data_dir: Path | None = None) -> AppService:
    data_dir = user_data_dir or get_user_data_dir()
    conn = connect_db(data_dir / "app.db")
    initialize_schema(conn)
    config = load_config(data_dir)
    stock_master = StockMaster(conn)
    calendar = TradeCalendar(conn)
    return AppService(conn, config, stock_master, calendar)

