from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pypinyin import Style, lazy_pinyin

from ptrade_order_tool.data.tushare_client import TushareProClient


class MissingTushareToken(RuntimeError):
    pass


@dataclass(slots=True)
class StockRow:
    ts_code: str
    symbol: str
    name: str
    list_status: str = "L"


class StockMaster:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_stock_basic(self, rows: Iterable[dict[str, str] | StockRow], updated_on: str) -> None:
        prepared = []
        for row in rows:
            stock = row if isinstance(row, StockRow) else StockRow(**row)
            name_pinyin = "".join(lazy_pinyin(stock.name)).lower()
            name_initials = "".join(lazy_pinyin(stock.name, style=Style.FIRST_LETTER)).lower()
            prepared.append(
                (
                    stock.ts_code,
                    stock.symbol,
                    stock.name,
                    name_pinyin,
                    name_initials,
                    stock.list_status,
                    updated_on,
                )
            )

        self.conn.executemany(
            """
            insert into stock_basic (
                ts_code, symbol, name, name_pinyin, name_initials, list_status, updated_on
            ) values (?, ?, ?, ?, ?, ?, ?)
            on conflict(ts_code) do update set
                symbol = excluded.symbol,
                name = excluded.name,
                name_pinyin = excluded.name_pinyin,
                name_initials = excluded.name_initials,
                list_status = excluded.list_status,
                updated_on = excluded.updated_on
            """,
            prepared,
        )
        self.conn.commit()

    def sync_from_tushare(self, token: str, updated_on: str, pro_client: Any | None = None) -> int:
        if pro_client is None:
            pro_client = TushareProClient(token)

        result = pro_client.query(
            "stock_basic",
            fields="ts_code,symbol,name,list_status",
        )
        if hasattr(result, "to_dict"):
            rows = result.to_dict("records")
        else:
            rows = list(result)
        self.upsert_stock_basic(rows, updated_on=updated_on)
        return len(rows)

    def has_any_stock_data(self) -> bool:
        row = self.conn.execute("select 1 from stock_basic limit 1").fetchone()
        return row is not None

    def last_updated_on(self) -> str:
        row = self.conn.execute("select max(updated_on) as updated_on from stock_basic").fetchone()
        return str(row["updated_on"] or "") if row else ""

    def resolve_stock(self, query: str) -> dict[str, str] | None:
        text = query.strip()
        if not text:
            return None
        row = self.conn.execute(
            """
            select ts_code, symbol, name, list_status
            from stock_basic
            where list_status = 'L'
              and (ts_code = ? or symbol = ? or name = ?)
            order by ts_code
            limit 1
            """,
            (text, text, text),
        ).fetchone()
        return dict(row) if row else None

    def search_stocks(self, query: str, limit: int = 20) -> list[dict[str, str]]:
        text = query.strip().lower()
        if not text:
            return []
        like = f"%{text}%"
        rows = self.conn.execute(
            """
            select ts_code, symbol, name, list_status
            from stock_basic
            where list_status = 'L'
              and (
                lower(ts_code) like ?
                or lower(symbol) like ?
                or lower(name) like ?
                or lower(name_pinyin) like ?
                or lower(name_initials) like ?
              )
            order by
              case
                when lower(symbol) = ? then 0
                when lower(ts_code) = ? then 1
                when lower(name) = ? then 2
                else 3
              end,
              ts_code
            limit ?
            """,
            (like, like, like, like, like, text, text, text, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_button_state(self, today: str, is_trade_day: bool) -> str:
        if not self.has_any_stock_data():
            return "generate"
        if self.last_updated_on() == today:
            return "updated_disabled"
        if not is_trade_day:
            return "update_disabled_non_trade_day"
        return "update_enabled"


def load_tushare_token(executable_dir: Path, user_data_dir: Path) -> str:
    token = os.environ.get("TUSHARE_TOKEN")
    if token:
        return token

    for env_path in (executable_dir / ".env", user_data_dir / ".env"):
        if env_path.exists():
            value = _read_env_value(env_path, "TUSHARE_TOKEN")
            if value:
                return value

    raise MissingTushareToken(".env 或环境变量里没有 TUSHARE_TOKEN")


def save_tushare_token(user_data_dir: Path, token: str) -> Path:
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("TUSHARE_TOKEN 不能为空")
    user_data_dir.mkdir(parents=True, exist_ok=True)
    env_path = user_data_dir / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    output: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith("TUSHARE_TOKEN="):
            output.append(f"TUSHARE_TOKEN={cleaned}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"TUSHARE_TOKEN={cleaned}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return env_path


def _read_env_value(env_path: Path, key: str) -> str:
    prefix = f"{key}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix):].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return ""
