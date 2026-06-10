from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.order_exporter import export_order_json, validate_export
from ptrade_order_tool.data.ptrade_importer import StockMatcher, parse_ptrade_json
from ptrade_order_tool.data.stock_master import load_tushare_token
from ptrade_order_tool.data.trade_calendar import TradeCalendar
from ptrade_order_tool.logging_utils import get_logger
from ptrade_order_tool.models import ExportValidation, OrderType, SessionDraft


PTRADER_JSON_RE = re.compile(r"^\d{8}\.json$")


@dataclass(slots=True)
class StartupResult:
    draft: SessionDraft | None
    message: str


class AppService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        config: AppConfig,
        stock_matcher: StockMatcher,
        calendar: TradeCalendar,
    ) -> None:
        self.conn = conn
        self.config = config
        self.stock_matcher = stock_matcher
        self.calendar = calendar
        self.drafts = DraftStore(conn)
        self.logger = get_logger()

    def open_latest_on_startup(self) -> StartupResult:
        latest_path = find_latest_ptrade_json(self.config.ptrade_data_dir)
        if latest_path is None:
            self.logger.info("startup_open_latest missing ptrade_data_dir=%s", self.config.ptrade_data_dir)
            return StartupResult(None, "未找到可导入的 Ptrade 盘后 JSON")
        self.logger.info("startup_open_latest path=%s", latest_path)
        return StartupResult(self._create_or_open_from_path(latest_path, overwrite=False), "已打开最新管理日期")

    def reimport_manage_date(self, ptrade_json_path: Path) -> SessionDraft:
        return self._create_or_open_from_path(ptrade_json_path, overwrite=True)

    def import_ptrade_json(self, ptrade_json_path: Path) -> SessionDraft:
        return self._create_or_open_from_path(ptrade_json_path, overwrite=False)

    def reimport_current_draft(self, manage_date: str) -> SessionDraft:
        draft = self.drafts.load_draft(manage_date)
        if not draft.ptrade_json_path:
            raise ValueError("当前日期没有源 Ptrade JSON 路径")
        return self._create_or_open_from_path(Path(draft.ptrade_json_path), overwrite=True)

    def load_draft(self, manage_date: str) -> SessionDraft:
        return self.drafts.load_draft(manage_date)

    def list_manage_dates(self) -> list[str]:
        return self.drafts.list_manage_dates()

    def update_config(self, config: AppConfig) -> None:
        self.config = config

    def update_and_confirm_order(
        self,
        order_id: int,
        *,
        price: Decimal,
        shares: int,
        order_type: OrderType,
    ) -> SessionDraft:
        self.drafts.save_order_change(order_id, price=price, shares=shares, order_type=order_type)
        self.drafts.confirm_order(order_id)
        manage_date = self._manage_date_for_order(order_id)
        self.logger.info("order_confirmed manage_date=%s order_id=%s type=%s price=%s shares=%s", manage_date, order_id, order_type, price, shares)
        return self.drafts.load_draft(manage_date)

    def update_order_change(
        self,
        order_id: int,
        *,
        price: Decimal,
        shares: int,
        order_type: OrderType,
    ) -> SessionDraft:
        self.drafts.save_order_change(order_id, price=price, shares=shares, order_type=order_type)
        manage_date = self._manage_date_for_order(order_id)
        self.logger.info("order_changed manage_date=%s order_id=%s type=%s price=%s shares=%s", manage_date, order_id, order_type, price, shares)
        return self.drafts.load_draft(manage_date)

    def add_order(
        self,
        manage_date: str,
        *,
        ts_code: str,
        stock_name: str,
        order_type: OrderType,
    ) -> SessionDraft:
        self.drafts.add_order(
            manage_date,
            ts_code,
            stock_name,
            order_type,
            Decimal("0"),
            0,
            confirmed=False,
            source="manual",
        )
        self.logger.info("order_added manage_date=%s ts_code=%s type=%s", manage_date, ts_code, order_type)
        return self.drafts.load_draft(manage_date)

    def add_manual_stock(self, manage_date: str, query: str) -> SessionDraft:
        candidates = self.search_manual_stock_candidates(query, limit=2)
        stock = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            raise ValueError(f"存在多个股票候选: {query}")
        if not stock:
            raise ValueError(f"未找到股票: {query}")
        return self.add_manual_stock_by_code(manage_date, stock["ts_code"], stock_name=stock["name"])

    def add_manual_stock_by_code(self, manage_date: str, ts_code: str, *, stock_name: str = "") -> SessionDraft:
        stock = self.stock_matcher.resolve_stock(ts_code)
        if not stock and not stock_name:
            raise ValueError(f"未找到股票: {ts_code}")
        self.drafts.add_manual_stock(
            manage_date,
            stock["ts_code"] if stock else ts_code,
            stock["name"] if stock else stock_name,
        )
        self.logger.info("manual_stock_added manage_date=%s ts_code=%s", manage_date, stock["ts_code"] if stock else ts_code)
        return self.drafts.load_draft(manage_date)

    def search_manual_stock_candidates(self, query: str, *, limit: int = 20) -> list[dict[str, str]]:
        stock = self.stock_matcher.resolve_stock(query)
        if stock:
            return [stock]
        if hasattr(self.stock_matcher, "search_stocks"):
            return self.stock_matcher.search_stocks(query, limit=limit)
        return []

    def stock_update_button_state(self, today: str) -> str:
        if not self.calendar.has_calendar_for(today):
            if hasattr(self.stock_matcher, "has_any_stock_data") and self.stock_matcher.has_any_stock_data():
                return "update_enabled"
            return "generate"
        if not hasattr(self.stock_matcher, "update_button_state"):
            return "generate"
        return self.stock_matcher.update_button_state(today, self.calendar.is_trade_day(today))

    def ensure_trade_calendar(
        self,
        *,
        today: str,
        executable_dir: Path,
        user_data_dir: Path,
        pro_client=None,
    ) -> int:
        if self.calendar.has_calendar_for(today):
            return 0
        token = load_tushare_token(executable_dir, user_data_dir)
        return self.calendar.sync_from_tushare(token, today=today, pro_client=pro_client)

    def update_stock_basic(
        self,
        *,
        today: str,
        executable_dir: Path,
        user_data_dir: Path,
        pro_client=None,
    ) -> int:
        if not hasattr(self.stock_matcher, "sync_from_tushare"):
            raise TypeError("stock_matcher does not support Tushare sync")
        token = load_tushare_token(executable_dir, user_data_dir)
        if not self.calendar.has_calendar_for(today):
            self.calendar.sync_from_tushare(token, today=today, pro_client=pro_client)
        if not self.calendar.is_trade_day(today) and getattr(self.stock_matcher, "has_any_stock_data", lambda: False)():
            return 0
        return self.stock_matcher.sync_from_tushare(token, updated_on=today, pro_client=pro_client)

    def delete_order(self, order_id: int) -> SessionDraft:
        manage_date = self._manage_date_for_order(order_id)
        self.drafts.delete_order(order_id)
        self.logger.info("order_deleted manage_date=%s order_id=%s", manage_date, order_id)
        return self.drafts.load_draft(manage_date)

    def delete_order_with_snapshot(self, order_id: int) -> tuple[SessionDraft, dict[str, Any]]:
        manage_date = self._manage_date_for_order(order_id)
        snapshot = self.drafts.delete_order(order_id)
        self.logger.info("order_deleted manage_date=%s order_id=%s", manage_date, order_id)
        return self.drafts.load_draft(manage_date), snapshot

    def restore_deleted_order(self, snapshot: dict[str, Any]) -> SessionDraft:
        self.drafts.restore_deleted_order(snapshot)
        self.logger.info("order_restored manage_date=%s ts_code=%s", snapshot["manage_date"], snapshot["ts_code"])
        return self.drafts.load_draft(str(snapshot["manage_date"]))

    def export_draft(self, manage_date: str, *, allow_overwrite: bool = False) -> ExportValidation:
        draft = self.drafts.load_draft(manage_date)
        validation = validate_export(draft)
        if not validation.can_export:
            return validation
        if not draft.export_json_path:
            validation.blockers.append("导出路径未配置")
            return validation
        export_order_json(draft, Path(draft.export_json_path), allow_overwrite=allow_overwrite)
        self.drafts.mark_exported(manage_date)
        self.logger.info("draft_exported manage_date=%s path=%s overwrite=%s", manage_date, draft.export_json_path, allow_overwrite)
        return validation

    def validate_draft_for_export(self, manage_date: str) -> ExportValidation:
        return validate_export(self.drafts.load_draft(manage_date))

    def _create_or_open_from_path(self, ptrade_json_path: Path, *, overwrite: bool) -> SessionDraft:
        imported = parse_ptrade_json(ptrade_json_path, self.stock_matcher)
        self.logger.info("ptrade_imported path=%s manage_date=%s holdings=%s overwrite=%s", ptrade_json_path, imported.manage_date, len(imported.holdings), overwrite)
        previous_day = self.calendar.previous_trade_day(imported.manage_date)
        expected_trade_date = self.calendar.next_trade_day(imported.manage_date)
        previous_order_path = None
        if previous_day and self.config.order_data_dir:
            previous_order_path = Path(self.config.order_data_dir) / f"{previous_day}.json"
        export_json_path = ""
        if self.config.order_data_dir:
            export_json_path = str(Path(self.config.order_data_dir) / f"{imported.manage_date}.json")
        return self.drafts.create_draft(
            imported,
            expected_trade_date=expected_trade_date,
            ptrade_json_path=str(ptrade_json_path),
            export_json_path=export_json_path,
            previous_order_path=previous_order_path,
            overwrite=overwrite,
        )

    def _manage_date_for_order(self, order_id: int) -> str:
        row = self.conn.execute("select manage_date from orders where id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError(f"Order not found: {order_id}")
        return str(row["manage_date"])


def find_latest_ptrade_json(ptrade_data_dir: str) -> Path | None:
    if not ptrade_data_dir:
        return None
    directory = Path(ptrade_data_dir)
    if not directory.exists() or not directory.is_dir():
        return None
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file() and PTRADER_JSON_RE.match(path.name)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stem)
