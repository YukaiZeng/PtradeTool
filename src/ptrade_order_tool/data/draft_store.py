from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ptrade_order_tool.models import (
    FundSnapshot,
    Holding,
    ImportedPtradeData,
    OrderDraft,
    OrderType,
    SessionDraft,
    StockDraft,
)


class DraftStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_draft(
        self,
        imported: ImportedPtradeData,
        *,
        expected_trade_date: str | None,
        ptrade_json_path: str,
        export_json_path: str,
        previous_order_path: Path | None = None,
        overwrite: bool = False,
    ) -> SessionDraft:
        existing = self._session_exists(imported.manage_date)
        if existing and not overwrite:
            return self.load_draft(imported.manage_date)

        now = datetime.now().isoformat(timespec="seconds")
        try:
            if existing and overwrite:
                self._delete_draft_without_commit(imported.manage_date)
            self.conn.execute(
                """
                insert into sessions (
                    manage_date, expected_trade_date, ptrade_json_path, export_json_path,
                    export_state, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    imported.manage_date,
                    expected_trade_date,
                    ptrade_json_path,
                    export_json_path,
                    "draft",
                    now,
                    now,
                ),
            )
            self._insert_fund(imported.manage_date, imported.fund)
            for holding in imported.holdings:
                self._insert_holding(imported.manage_date, holding)

            inherited_orders = self._load_inherited_sell_orders(previous_order_path)
            for holding in imported.holdings:
                for order in inherited_orders.get(holding.ts_code, []):
                    self._add_order_without_commit(
                        imported.manage_date,
                        holding.ts_code,
                        holding.stock_name,
                        order["order_type"],
                        Decimal(str(order["price"])),
                        holding.current_amount,
                        confirmed=False,
                        source="inherited",
                        warning="数量已按当前持仓调整，需确认",
                    )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.load_draft(imported.manage_date)

    def delete_draft(self, manage_date: str) -> None:
        self._delete_draft_without_commit(manage_date)
        self.conn.commit()

    def _delete_draft_without_commit(self, manage_date: str) -> None:
        for table in ("orders", "holdings", "draft_stocks", "fund_snapshots", "sessions"):
            self.conn.execute(f"delete from {table} where manage_date = ?", (manage_date,))

    def load_draft(self, manage_date: str) -> SessionDraft:
        session_row = self.conn.execute(
            "select * from sessions where manage_date = ?",
            (manage_date,),
        ).fetchone()
        if not session_row:
            raise KeyError(f"Draft not found: {manage_date}")

        fund_row = self.conn.execute(
            "select * from fund_snapshots where manage_date = ?",
            (manage_date,),
        ).fetchone()
        fund = FundSnapshot(
            cash=Decimal(str(fund_row["cash"])),
            positions_value=Decimal(str(fund_row["positions_value"])),
            portfolio_value=Decimal(str(fund_row["portfolio_value"])),
            stock_positions_value=Decimal(str(fund_row["stock_positions_value"])),
            calibrated_cash=Decimal(str(fund_row["calibrated_cash"])),
        )

        holdings = {
            row["ts_code"]: self._holding_from_row(row)
            for row in self.conn.execute(
                "select * from holdings where manage_date = ? order by ts_code",
                (manage_date,),
            ).fetchall()
        }
        orders_by_stock: dict[str, list[OrderDraft]] = {ts_code: [] for ts_code in holdings}
        stock_names_by_stock: dict[str, str] = {}
        for row in self.conn.execute(
            "select * from orders where manage_date = ? order by ts_code, sort_order, id",
            (manage_date,),
        ).fetchall():
            orders_by_stock.setdefault(row["ts_code"], []).append(self._order_from_row(row))
            stock_names_by_stock[row["ts_code"]] = row["stock_name"]

        stocks = [
            StockDraft(
                ts_code=ts_code,
                stock_name=holding.stock_name,
                is_holding=True,
                holding=holding,
                orders=orders_by_stock.get(ts_code, []),
            )
            for ts_code, holding in holdings.items()
        ]
        manual_stock_rows = self.conn.execute(
            """
            select ts_code, stock_name
            from draft_stocks
            where manage_date = ?
            order by ts_code
            """,
            (manage_date,),
        ).fetchall()
        for row in manual_stock_rows:
            if row["ts_code"] not in holdings:
                stocks.append(
                    StockDraft(
                        ts_code=row["ts_code"],
                        stock_name=row["stock_name"],
                        is_holding=False,
                        orders=orders_by_stock.get(row["ts_code"], []),
                    )
                )
        for ts_code, orders in orders_by_stock.items():
            if ts_code not in holdings and not any(stock.ts_code == ts_code for stock in stocks):
                stocks.append(
                    StockDraft(
                        ts_code=ts_code,
                        stock_name=stock_names_by_stock.get(ts_code, ts_code),
                        is_holding=False,
                        orders=orders,
                    )
                )

        return SessionDraft(
            manage_date=manage_date,
            expected_trade_date=session_row["expected_trade_date"],
            fund=fund,
            stocks=stocks,
            ptrade_json_path=session_row["ptrade_json_path"],
            export_json_path=session_row["export_json_path"],
            export_state=session_row["export_state"],
            read_only=self.is_read_only(manage_date),
        )

    def add_order(
        self,
        manage_date: str,
        ts_code: str,
        stock_name: str,
        order_type: OrderType,
        price: Decimal,
        shares: int,
        *,
        confirmed: bool = False,
        source: str = "manual",
        warning: str = "",
    ) -> int:
        row_id = self._add_order_without_commit(
            manage_date,
            ts_code,
            stock_name,
            order_type,
            price,
            shares,
            confirmed=confirmed,
            source=source,
            warning=warning,
        )
        self.conn.commit()
        return row_id

    def _add_order_without_commit(
        self,
        manage_date: str,
        ts_code: str,
        stock_name: str,
        order_type: OrderType,
        price: Decimal,
        shares: int,
        *,
        confirmed: bool = False,
        source: str = "manual",
        warning: str = "",
    ) -> int:
        sort_order = self._next_sort_order(manage_date, ts_code, order_type)
        cursor = self.conn.execute(
            """
            insert into orders (
                manage_date, ts_code, stock_name, order_type, price, shares,
                confirmed, source, warning, sort_order
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manage_date,
                ts_code,
                stock_name,
                order_type,
                float(price),
                int(shares),
                1 if confirmed else 0,
                source,
                warning,
                sort_order,
            ),
        )
        self._mark_modified(manage_date)
        return int(cursor.lastrowid)

    def add_manual_stock(self, manage_date: str, ts_code: str, stock_name: str) -> None:
        self.conn.execute(
            """
            insert into draft_stocks (manage_date, ts_code, stock_name, created_at)
            values (?, ?, ?, ?)
            on conflict(manage_date, ts_code) do update set
                stock_name = excluded.stock_name
            """,
            (manage_date, ts_code, stock_name, datetime.now().isoformat(timespec="seconds")),
        )
        self._mark_modified(manage_date)
        self.conn.commit()

    def save_order_change(self, order_id: int, *, price: Decimal, shares: int, order_type: OrderType) -> None:
        row = self.conn.execute("select manage_date from orders where id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError(f"Order not found: {order_id}")
        self.conn.execute(
            """
            update orders
            set price = ?, shares = ?, order_type = ?, confirmed = 0
            where id = ?
            """,
            (float(price), int(shares), order_type, order_id),
        )
        self._mark_modified(row["manage_date"])
        self.conn.commit()

    def confirm_order(self, order_id: int) -> None:
        row = self.conn.execute("select manage_date from orders where id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError(f"Order not found: {order_id}")
        self.conn.execute("update orders set confirmed = 1 where id = ?", (order_id,))
        self._mark_modified(row["manage_date"])
        self.conn.commit()

    def delete_order(self, order_id: int) -> dict[str, Any]:
        row = self.conn.execute("select * from orders where id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError(f"Order not found: {order_id}")
        snapshot = dict(row)
        self.conn.execute("delete from orders where id = ?", (order_id,))
        self._mark_modified(row["manage_date"])
        self.conn.commit()
        return snapshot

    def delete_stock(self, manage_date: str, ts_code: str) -> dict[str, Any]:
        holding_row = self.conn.execute(
            "select * from holdings where manage_date = ? and ts_code = ?",
            (manage_date, ts_code),
        ).fetchone()
        draft_stock_row = self.conn.execute(
            "select * from draft_stocks where manage_date = ? and ts_code = ?",
            (manage_date, ts_code),
        ).fetchone()
        order_rows = self.conn.execute(
            "select * from orders where manage_date = ? and ts_code = ? order by sort_order, id",
            (manage_date, ts_code),
        ).fetchall()
        if not holding_row and not draft_stock_row and not order_rows:
            raise KeyError(f"Stock not found: {manage_date} {ts_code}")
        snapshot = {
            "kind": "stock",
            "manage_date": manage_date,
            "ts_code": ts_code,
            "holding": dict(holding_row) if holding_row else None,
            "draft_stock": dict(draft_stock_row) if draft_stock_row else None,
            "orders": [dict(row) for row in order_rows],
        }
        for table in ("orders", "holdings", "draft_stocks"):
            self.conn.execute(
                f"delete from {table} where manage_date = ? and ts_code = ?",
                (manage_date, ts_code),
            )
        self._mark_modified(manage_date)
        self.conn.commit()
        return snapshot

    def restore_deleted_order(self, snapshot: dict[str, Any]) -> int:
        if snapshot.get("kind") == "stock":
            self.restore_deleted_stock(snapshot)
            return 0
        cursor = self.conn.execute(
            """
            insert into orders (
                manage_date, ts_code, stock_name, order_type, price, shares,
                confirmed, source, warning, sort_order
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["manage_date"],
                snapshot["ts_code"],
                snapshot["stock_name"],
                snapshot["order_type"],
                snapshot["price"],
                snapshot["shares"],
                snapshot["confirmed"],
                snapshot["source"],
                snapshot["warning"],
                snapshot["sort_order"],
            ),
        )
        self._mark_modified(snapshot["manage_date"])
        self.conn.commit()
        return int(cursor.lastrowid)

    def restore_deleted_stock(self, snapshot: dict[str, Any]) -> None:
        holding = snapshot.get("holding")
        if holding:
            self.conn.execute(
                """
                insert into holdings (
                    manage_date, ts_code, stock_code, stock_name, current_amount,
                    enable_amount, last_price, cost_price, market_value,
                    profit_ratio, income_balance, is_stock
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    holding["manage_date"],
                    holding["ts_code"],
                    holding["stock_code"],
                    holding["stock_name"],
                    holding["current_amount"],
                    holding["enable_amount"],
                    holding["last_price"],
                    holding["cost_price"],
                    holding["market_value"],
                    holding["profit_ratio"],
                    holding["income_balance"],
                    holding["is_stock"],
                ),
            )
        draft_stock = snapshot.get("draft_stock")
        if draft_stock:
            self.conn.execute(
                """
                insert into draft_stocks (manage_date, ts_code, stock_name, created_at)
                values (?, ?, ?, ?)
                """,
                (
                    draft_stock["manage_date"],
                    draft_stock["ts_code"],
                    draft_stock["stock_name"],
                    draft_stock["created_at"],
                ),
            )
        for order in snapshot.get("orders", []):
            self.conn.execute(
                """
                insert into orders (
                    manage_date, ts_code, stock_name, order_type, price, shares,
                    confirmed, source, warning, sort_order
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["manage_date"],
                    order["ts_code"],
                    order["stock_name"],
                    order["order_type"],
                    order["price"],
                    order["shares"],
                    order["confirmed"],
                    order["source"],
                    order["warning"],
                    order["sort_order"],
                ),
            )
        self._mark_modified(snapshot["manage_date"])
        self.conn.commit()

    def is_read_only(self, manage_date: str) -> bool:
        row = self.conn.execute("select max(manage_date) as latest from sessions").fetchone()
        latest = row["latest"] if row else None
        return bool(latest and manage_date < latest)

    def mark_exported(self, manage_date: str) -> None:
        self.conn.execute(
            "update sessions set export_state = 'exported', updated_at = ? where manage_date = ?",
            (datetime.now().isoformat(timespec="seconds"), manage_date),
        )
        self.conn.commit()

    def list_manage_dates(self) -> list[str]:
        rows = self.conn.execute(
            "select manage_date from sessions order by manage_date desc"
        ).fetchall()
        return [str(row["manage_date"]) for row in rows]

    def _session_exists(self, manage_date: str) -> bool:
        row = self.conn.execute(
            "select 1 from sessions where manage_date = ?",
            (manage_date,),
        ).fetchone()
        return row is not None

    def _insert_fund(self, manage_date: str, fund: FundSnapshot) -> None:
        self.conn.execute(
            """
            insert into fund_snapshots (
                manage_date, cash, positions_value, portfolio_value,
                stock_positions_value, calibrated_cash
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                manage_date,
                float(fund.cash),
                float(fund.positions_value),
                float(fund.portfolio_value),
                float(fund.stock_positions_value),
                float(fund.calibrated_cash),
            ),
        )

    def _insert_holding(self, manage_date: str, holding: Holding) -> None:
        self.conn.execute(
            """
            insert into holdings (
                manage_date, ts_code, stock_code, stock_name, current_amount,
                enable_amount, last_price, cost_price, market_value,
                profit_ratio, income_balance, is_stock
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manage_date,
                holding.ts_code,
                holding.stock_code,
                holding.stock_name,
                holding.current_amount,
                holding.enable_amount,
                float(holding.last_price),
                float(holding.cost_price),
                float(holding.market_value),
                float(holding.profit_ratio),
                float(holding.income_balance),
                1 if holding.is_stock else 0,
            ),
        )

    def _holding_from_row(self, row: sqlite3.Row) -> Holding:
        return Holding(
            ts_code=row["ts_code"],
            stock_code=row["stock_code"],
            stock_name=row["stock_name"],
            current_amount=row["current_amount"],
            enable_amount=row["enable_amount"],
            last_price=Decimal(str(row["last_price"])),
            cost_price=Decimal(str(row["cost_price"])),
            market_value=Decimal(str(row["market_value"])),
            profit_ratio=Decimal(str(row["profit_ratio"])),
            income_balance=Decimal(str(row["income_balance"])),
            is_stock=bool(row["is_stock"]),
        )

    def _order_from_row(self, row: sqlite3.Row) -> OrderDraft:
        return OrderDraft(
            id=row["id"],
            order_type=row["order_type"],
            price=Decimal(str(row["price"])),
            shares=row["shares"],
            confirmed=bool(row["confirmed"]),
            source=row["source"],
            warning=row["warning"],
            sort_order=row["sort_order"],
        )

    def _load_inherited_sell_orders(self, previous_order_path: Path | None) -> dict[str, list[dict[str, Any]]]:
        if not previous_order_path or not previous_order_path.exists():
            return {}
        try:
            data = json.loads(previous_order_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        inherited: dict[str, list[dict[str, Any]]] = {}
        for ts_code, stock_info in data.items():
            if not isinstance(stock_info, dict):
                continue
            for order_type in ("sell_profit", "sell_loss"):
                orders = stock_info.get(order_type, [])
                if not isinstance(orders, list):
                    continue
                for order in orders:
                    if not isinstance(order, dict):
                        continue
                    if "price" not in order or "shares" not in order:
                        continue
                    inherited.setdefault(ts_code, []).append(
                        {
                            "order_type": order_type,
                            "price": order["price"],
                            "shares": order["shares"],
                        }
                    )
        return inherited

    def _next_sort_order(self, manage_date: str, ts_code: str, order_type: str) -> int:
        row = self.conn.execute(
            """
            select coalesce(max(sort_order), 0) + 1 as next_sort
            from orders
            where manage_date = ? and ts_code = ? and order_type = ?
            """,
            (manage_date, ts_code, order_type),
        ).fetchone()
        return int(row["next_sort"])

    def _mark_modified(self, manage_date: str) -> None:
        row = self.conn.execute(
            "select export_state from sessions where manage_date = ?",
            (manage_date,),
        ).fetchone()
        export_state = "modified_after_export" if row and row["export_state"] == "exported" else "draft"
        self.conn.execute(
            "update sessions set export_state = ?, updated_at = ? where manage_date = ?",
            (export_state, datetime.now().isoformat(timespec="seconds"), manage_date),
        )
