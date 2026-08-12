from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from ptrade_order_tool.data.tushare_client import TushareProClient
from ptrade_order_tool.models import DailyQuote


DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"


class DailyQuoteStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_daily_quotes(self, rows: Iterable[dict[str, object]], updated_at: str) -> None:
        prepared = []
        for row in rows:
            prepared.append(
                (
                    str(row["trade_date"]),
                    str(row["ts_code"]),
                    _decimal_text(row["open"]),
                    _decimal_text(row["high"]),
                    _decimal_text(row["low"]),
                    _decimal_text(row["close"]),
                    _decimal_text(row["pre_close"]),
                    _decimal_text(row["change"]),
                    _decimal_text(row["pct_chg"]),
                    _decimal_text(row["vol"]),
                    _decimal_text(row["amount"]),
                    updated_at,
                )
            )
        if not prepared:
            return
        self.conn.executemany(
            """
            insert into daily_quotes (
                trade_date, ts_code, open, high, low, close, pre_close,
                change, pct_chg, vol, amount, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(trade_date, ts_code) do update set
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                pre_close = excluded.pre_close,
                change = excluded.change,
                pct_chg = excluded.pct_chg,
                vol = excluded.vol,
                amount = excluded.amount,
                updated_at = excluded.updated_at
            """,
            prepared,
        )
        self.conn.commit()

    def load_quotes(self, trade_date: str, ts_codes: Iterable[str] | None = None) -> dict[str, DailyQuote]:
        params: list[object] = [trade_date]
        where = "where trade_date = ?"
        codes = list(ts_codes or [])
        if codes:
            placeholders = ",".join("?" for _ in codes)
            where += f" and ts_code in ({placeholders})"
            params.extend(codes)
        rows = self.conn.execute(
            f"""
            select trade_date, ts_code, open, high, low, close, pre_close,
                   change, pct_chg, vol, amount
            from daily_quotes
            {where}
            """,
            params,
        ).fetchall()
        return {str(row["ts_code"]): _quote_from_row(row) for row in rows}

    def has_trade_date(self, trade_date: str) -> bool:
        row = self.conn.execute(
            "select 1 from daily_quotes where trade_date = ? limit 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    def ts_codes_to_fetch(self, trade_date: str, ts_codes: Iterable[str], *, now: datetime | None = None) -> list[str]:
        codes = list(dict.fromkeys(ts_codes))
        if not codes:
            return []
        placeholders = ",".join("?" for _ in codes)
        timestamp = (now or datetime.now()).isoformat(timespec="seconds")
        rows = self.conn.execute(
            f"""
            select ts_code from daily_quotes
            where trade_date = ? and ts_code in ({placeholders})
            union
            select ts_code from daily_quote_fetch_state
            where trade_date = ? and status = 'no_data' and next_retry_at > ?
              and ts_code in ({placeholders})
            """,
            (trade_date, *codes, trade_date, timestamp, *codes),
        ).fetchall()
        completed = {str(row["ts_code"]) for row in rows}
        return [ts_code for ts_code in codes if ts_code not in completed]

    def record_fetch_result(
        self,
        trade_date: str,
        *,
        requested_ts_codes: Iterable[str],
        rows: Iterable[dict[str, object]],
        successful_ts_codes: Iterable[str],
        now: datetime | None = None,
    ) -> None:
        requested = list(dict.fromkeys(requested_ts_codes))
        succeeded = set(successful_ts_codes).intersection(requested)
        fetched_rows = list(rows)
        returned_codes = {str(row.get("ts_code", "")) for row in fetched_rows}
        moment = now or datetime.now()
        updated_at = moment.strftime("%Y%m%d%H%M%S")
        retry_at = (moment + timedelta(minutes=30)).isoformat(timespec="seconds")
        try:
            self._upsert_daily_quotes_without_commit(fetched_rows, updated_at=updated_at)
            if returned_codes:
                placeholders = ",".join("?" for _ in returned_codes)
                self.conn.execute(
                    f"delete from daily_quote_fetch_state where trade_date = ? and ts_code in ({placeholders})",
                    (trade_date, *returned_codes),
                )
            no_data_codes = succeeded - returned_codes
            self.conn.executemany(
                """
                insert into daily_quote_fetch_state (trade_date, ts_code, status, next_retry_at, updated_at)
                values (?, ?, 'no_data', ?, ?)
                on conflict(trade_date, ts_code) do update set
                    status = excluded.status,
                    next_retry_at = excluded.next_retry_at,
                    updated_at = excluded.updated_at
                """,
                [(trade_date, ts_code, retry_at, updated_at) for ts_code in no_data_codes],
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def sync_trade_date_from_tushare(
        self,
        token: str,
        trade_date: str,
        pro_client: Any | None = None,
    ) -> int:
        if pro_client is None:
            pro_client = TushareProClient(token)
        result = pro_client.query("daily", trade_date=trade_date, fields=DAILY_FIELDS)
        rows = result.to_dict("records") if hasattr(result, "to_dict") else list(result)
        self.upsert_daily_quotes(rows, updated_at=datetime.now().strftime("%Y%m%d%H%M%S"))
        return len(rows)

    def _upsert_daily_quotes_without_commit(self, rows: Iterable[dict[str, object]], *, updated_at: str) -> None:
        prepared = []
        for row in rows:
            prepared.append(
                (
                    str(row["trade_date"]), str(row["ts_code"]), _decimal_text(row["open"]),
                    _decimal_text(row["high"]), _decimal_text(row["low"]), _decimal_text(row["close"]),
                    _decimal_text(row["pre_close"]), _decimal_text(row["change"]), _decimal_text(row["pct_chg"]),
                    _decimal_text(row["vol"]), _decimal_text(row["amount"]), updated_at,
                )
            )
        if not prepared:
            return
        self.conn.executemany(
            """
            insert into daily_quotes (trade_date, ts_code, open, high, low, close, pre_close, change, pct_chg, vol, amount, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(trade_date, ts_code) do update set
                open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
                pre_close = excluded.pre_close, change = excluded.change, pct_chg = excluded.pct_chg,
                vol = excluded.vol, amount = excluded.amount, updated_at = excluded.updated_at
            """,
            prepared,
        )


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _decimal_text(value: object) -> str:
    return format(_decimal(value), "f")


def _quote_from_row(row) -> DailyQuote:
    return DailyQuote(
        ts_code=str(row["ts_code"]),
        trade_date=str(row["trade_date"]),
        open=_decimal(row["open"]),
        high=_decimal(row["high"]),
        low=_decimal(row["low"]),
        close=_decimal(row["close"]),
        pre_close=_decimal(row["pre_close"]),
        change=_decimal(row["change"]),
        pct_chg=_decimal(row["pct_chg"]),
        vol=_decimal(row["vol"]),
        amount=_decimal(row["amount"]),
    )
