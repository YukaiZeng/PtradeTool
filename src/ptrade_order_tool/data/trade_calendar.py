from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Iterable

from ptrade_order_tool.data.tushare_client import TushareProClient


class TradeCalendar:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_trade_calendar(self, rows: Iterable[dict[str, str | int]], updated_on: str) -> None:
        prepared = [
            (str(row["cal_date"]), int(row["is_open"]), updated_on)
            for row in rows
        ]
        self.conn.executemany(
            """
            insert into trade_calendar (cal_date, is_open, updated_on)
            values (?, ?, ?)
            on conflict(cal_date) do update set
                is_open = excluded.is_open,
                updated_on = excluded.updated_on
            """,
            prepared,
        )
        self.conn.commit()

    def is_trade_day(self, date_str: str) -> bool:
        row = self.conn.execute(
            "select is_open from trade_calendar where cal_date = ?",
            (date_str,),
        ).fetchone()
        return bool(row and row["is_open"] == 1)

    def previous_trade_day(self, date_str: str) -> str | None:
        row = self.conn.execute(
            """
            select cal_date
            from trade_calendar
            where cal_date < ? and is_open = 1
            order by cal_date desc
            limit 1
            """,
            (date_str,),
        ).fetchone()
        return str(row["cal_date"]) if row else None

    def next_trade_day(self, date_str: str) -> str | None:
        row = self.conn.execute(
            """
            select cal_date
            from trade_calendar
            where cal_date > ? and is_open = 1
            order by cal_date asc
            limit 1
            """,
            (date_str,),
        ).fetchone()
        return str(row["cal_date"]) if row else None

    def has_calendar_for(self, date_str: str) -> bool:
        row = self.conn.execute(
            "select 1 from trade_calendar where cal_date = ?",
            (date_str,),
        ).fetchone()
        return row is not None

    def sync_from_tushare(self, token: str, today: str, pro_client: Any | None = None) -> int:
        if pro_client is None:
            pro_client = TushareProClient(token)

        year = int(today[:4])
        result = pro_client.query(
            "trade_cal",
            start_date=f"{year}0101",
            end_date=f"{year + 1}1231",
            fields="cal_date,is_open",
        )
        if hasattr(result, "to_dict"):
            rows = result.to_dict("records")
        else:
            rows = list(result)
        self.upsert_trade_calendar(rows, updated_on=datetime.now().strftime("%Y%m%d"))
        return len(rows)
