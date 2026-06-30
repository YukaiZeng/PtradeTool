from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.data.daily_quote_store import DailyQuoteStore
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.order_exporter import ORDER_TYPES, build_order_json, export_order_json, validate_export
from ptrade_order_tool.data.ptrade_importer import StockMatcher, parse_ptrade_json
from ptrade_order_tool.data.stock_master import load_tushare_token
from ptrade_order_tool.data.trade_calendar import TradeCalendar
from ptrade_order_tool.logging_utils import get_logger
from ptrade_order_tool.models import DailyQuote, ExportValidation, FundSnapshot, Holding, ImportedPtradeData, OrderType, SessionDraft


PTRADER_JSON_RE = re.compile(r"^\d{8}\.json$")
CURRENT_TRADE_DAY_CUTOFF = time(17, 30)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class StartupResult:
    draft: SessionDraft | None
    message: str


@dataclass(slots=True)
class JsonSyncPlan:
    manage_date: str
    ptrade_json_path: Path | None = None
    order_json_path: Path | None = None
    has_ptrade_changes: bool = False
    has_order_changes: bool = False

    @property
    def can_sync(self) -> bool:
        return self.has_ptrade_changes or self.has_order_changes


class AppService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        config: AppConfig,
        stock_matcher: StockMatcher,
        calendar: TradeCalendar,
        *,
        now_provider=None,
    ) -> None:
        self.conn = conn
        self.config = config
        self.stock_matcher = stock_matcher
        self.calendar = calendar
        self.drafts = DraftStore(conn)
        self.daily_quotes = DailyQuoteStore(conn)
        self._now_provider = now_provider or (lambda: datetime.now(BEIJING_TZ))
        self.logger = get_logger()

    def open_latest_on_startup(self, *, today: str | None = None, now: datetime | None = None) -> StartupResult:
        today = today or self._today(now)
        current_manage_date = self.current_editable_manage_date(today=today, now=now)
        target_path = find_ptrade_json_for_date(self.config.ptrade_data_dir, current_manage_date)
        if target_path is not None:
            self.logger.info("startup_open_latest path=%s", target_path)
            draft = self._create_or_open_from_path(target_path, overwrite=False)
            return StartupResult(self._with_read_only_state(draft, today=today, now=now), "已打开最新管理日期")
        try:
            draft = self.drafts.load_draft(current_manage_date)
        except KeyError:
            self.logger.info("startup_open_latest missing ptrade_data_dir=%s manage_date=%s", self.config.ptrade_data_dir, current_manage_date)
            draft = self.open_blank_manage_date(current_manage_date)
            return StartupResult(self._with_read_only_state(draft, today=today, now=now), "未找到盘后 JSON，已创建空白交易单")
        return StartupResult(self._with_read_only_state(draft, today=today, now=now), "已打开当前管理日期")

    def reimport_manage_date(self, ptrade_json_path: Path) -> SessionDraft:
        return self._create_or_open_from_path(ptrade_json_path, overwrite=True)

    def import_ptrade_json(self, ptrade_json_path: Path) -> SessionDraft:
        imported = parse_ptrade_json(ptrade_json_path, self.stock_matcher)
        overwrite = self._blank_draft_can_be_replaced(imported.manage_date, raise_on_edited=True)
        return self._create_or_open_imported(imported, ptrade_json_path, overwrite=overwrite)

    def reimport_current_draft(self, manage_date: str) -> SessionDraft:
        draft = self.drafts.load_draft(manage_date)
        if not draft.ptrade_json_path:
            raise ValueError("当前日期没有源 Ptrade JSON 路径")
        return self._create_or_open_from_path(Path(draft.ptrade_json_path), overwrite=True)

    def load_draft(self, manage_date: str) -> SessionDraft:
        return self._with_read_only_state(self.drafts.load_draft(manage_date))

    def open_blank_manage_date(self, manage_date: str) -> SessionDraft:
        return self._create_or_open_blank(manage_date)

    def empty_manage_date_view(self, manage_date: str) -> SessionDraft:
        return self._empty_draft(manage_date, export_state="empty")

    def list_manage_dates(self, *, today: str | None = None, now: datetime | None = None) -> list[str]:
        session_dates = set(self.drafts.list_manage_dates())
        today = today or self._today(now)
        latest_trade_date = self.current_editable_manage_date(today=today, now=now)
        start_date = self._manage_date_range_start(today=today, latest_trade_date=latest_trade_date)
        calendar_dates = set(self.calendar.trade_days_between(start_date, latest_trade_date))
        if not calendar_dates and not session_dates:
            calendar_dates.add(latest_trade_date)
        return sorted(session_dates | calendar_dates, reverse=True)

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
        self.drafts.save_and_confirm_order(order_id, price=price, shares=shares, order_type=order_type)
        manage_date = self._manage_date_for_order(order_id)
        self.logger.info("order_confirmed manage_date=%s order_id=%s type=%s price=%s shares=%s", manage_date, order_id, order_type, price, shares)
        return self.load_draft(manage_date)

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
        return self.load_draft(manage_date)

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
        return self.load_draft(manage_date)

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
        return self.load_draft(manage_date)

    def search_manual_stock_candidates(self, query: str, *, limit: int = 20) -> list[dict[str, str]]:
        text = query.strip()
        stock = self.stock_matcher.resolve_stock(text)
        if not stock and text != text.upper():
            stock = self.stock_matcher.resolve_stock(text.upper())
        if stock:
            return [stock]
        if hasattr(self.stock_matcher, "search_stocks"):
            return self.stock_matcher.search_stocks(text, limit=limit)
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
        return self.maintain_trade_calendar(
            today=today,
            executable_dir=executable_dir,
            user_data_dir=user_data_dir,
            pro_client=pro_client,
        )

    def maintain_trade_calendar(
        self,
        *,
        today: str,
        executable_dir: Path,
        user_data_dir: Path,
        pro_client=None,
    ) -> int:
        token = load_tushare_token(executable_dir, user_data_dir)
        start_date = self._calendar_sync_start_date(today)
        end_date = f"{int(today[:4]) + 1}1231"
        return self.calendar.sync_range_from_tushare(
            token,
            start_date=start_date,
            end_date=end_date,
            pro_client=pro_client,
        )

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
        self.maintain_trade_calendar(
            today=today,
            executable_dir=executable_dir,
            user_data_dir=user_data_dir,
            pro_client=pro_client,
        )
        if not self.calendar.is_trade_day(today) and getattr(self.stock_matcher, "has_any_stock_data", lambda: False)():
            return 0
        return self.stock_matcher.sync_from_tushare(token, updated_on=today, pro_client=pro_client)

    def stock_update_fetch_plan(
        self,
        *,
        today: str,
        executable_dir: Path,
        user_data_dir: Path,
    ) -> dict[str, str]:
        token = load_tushare_token(executable_dir, user_data_dir)
        return {
            "token": token,
            "today": today,
            "calendar_start_date": self._calendar_sync_start_date(today),
            "calendar_end_date": f"{int(today[:4]) + 1}1231",
        }

    def apply_stock_basic_update(
        self,
        *,
        today: str,
        calendar_rows: list[dict[str, object]],
        stock_rows: list[dict[str, object]],
    ) -> int:
        self.calendar.upsert_trade_calendar(calendar_rows, updated_on=today)
        if not self.calendar.is_trade_day(today) and getattr(self.stock_matcher, "has_any_stock_data", lambda: False)():
            return 0
        if not hasattr(self.stock_matcher, "upsert_stock_basic"):
            raise TypeError("stock_matcher does not support stock row upsert")
        self.stock_matcher.upsert_stock_basic(stock_rows, updated_on=today)
        return len(stock_rows)

    def delete_order(self, order_id: int) -> SessionDraft:
        manage_date = self._manage_date_for_order(order_id)
        self.drafts.delete_order(order_id)
        self.logger.info("order_deleted manage_date=%s order_id=%s", manage_date, order_id)
        return self.load_draft(manage_date)

    def delete_order_with_snapshot(self, order_id: int) -> tuple[SessionDraft, dict[str, Any]]:
        manage_date = self._manage_date_for_order(order_id)
        snapshot = self.drafts.delete_order(order_id)
        self.logger.info("order_deleted manage_date=%s order_id=%s", manage_date, order_id)
        return self.load_draft(manage_date), snapshot

    def delete_stock_with_snapshot(self, manage_date: str, ts_code: str) -> tuple[SessionDraft, dict[str, Any]]:
        snapshot = self.drafts.delete_stock(manage_date, ts_code)
        self.logger.info("stock_deleted manage_date=%s ts_code=%s", manage_date, ts_code)
        return self.load_draft(manage_date), snapshot

    def delete_manage_date(self, manage_date: str) -> None:
        self.drafts.delete_draft(manage_date)
        self.logger.info("manage_date_deleted manage_date=%s", manage_date)

    def restore_deleted_order(self, snapshot: dict[str, Any]) -> SessionDraft:
        self.drafts.restore_deleted_order(snapshot)
        self.logger.info("order_restored manage_date=%s ts_code=%s", snapshot["manage_date"], snapshot["ts_code"])
        return self.load_draft(str(snapshot["manage_date"]))

    def export_draft(self, manage_date: str, *, allow_overwrite: bool = False) -> ExportValidation:
        draft = self.load_draft(manage_date)
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
        return validate_export(self.load_draft(manage_date))

    def json_sync_plan(self, manage_date: str) -> JsonSyncPlan:
        plan = JsonSyncPlan(
            manage_date=manage_date,
            ptrade_json_path=find_ptrade_json_for_date(self.config.ptrade_data_dir, manage_date),
            order_json_path=find_order_json_for_date(self.config.order_data_dir, manage_date),
        )
        if not plan.ptrade_json_path and not plan.order_json_path:
            return plan
        try:
            draft = self.drafts.load_draft(manage_date)
        except KeyError:
            draft = self._empty_draft(manage_date, export_state="empty")
        if plan.ptrade_json_path:
            imported = parse_ptrade_json(plan.ptrade_json_path, self.stock_matcher)
            plan.has_ptrade_changes = self._ptrade_data_differs(imported, draft)
        if plan.order_json_path:
            order_data = self._load_order_json(plan.order_json_path)
            plan.has_order_changes = self._order_data_differs(order_data, draft)
        return plan

    def sync_json_to_draft(self, manage_date: str) -> SessionDraft:
        plan = self.json_sync_plan(manage_date)
        if not plan.ptrade_json_path and not plan.order_json_path:
            raise FileNotFoundError(f"No JSON found for manage date: {manage_date}")

        if plan.ptrade_json_path:
            imported = parse_ptrade_json(plan.ptrade_json_path, self.stock_matcher)
            export_json_path = self._export_json_path(manage_date)
            try:
                current = self.drafts.load_draft(manage_date)
                if current.export_json_path:
                    export_json_path = current.export_json_path
            except KeyError:
                pass
            self.drafts.sync_fund_and_holdings(
                imported,
                expected_trade_date=self.calendar.next_trade_day(manage_date),
                ptrade_json_path=str(plan.ptrade_json_path),
                export_json_path=export_json_path,
            )
        elif plan.order_json_path:
            try:
                self.drafts.load_draft(manage_date)
            except KeyError:
                self._create_or_open_blank(manage_date)

        if plan.order_json_path:
            self.drafts.replace_orders(manage_date, self._load_order_json(plan.order_json_path))
            self.drafts.mark_exported(manage_date)

        self.logger.info(
            "json_synced manage_date=%s ptrade_json=%s order_json=%s",
            manage_date,
            plan.ptrade_json_path,
            plan.order_json_path,
        )
        return self.load_draft(manage_date)

    def load_daily_quotes(
        self,
        trade_date: str,
        *,
        token: str | None = None,
        executable_dir: Path | None = None,
        user_data_dir: Path | None = None,
        pro_client=None,
        ts_codes: list[str] | None = None,
    ) -> dict[str, DailyQuote]:
        try:
            if not self.daily_quotes.has_trade_date(trade_date):
                resolved_token = token or load_tushare_token(executable_dir or Path.cwd(), user_data_dir or Path.cwd())
                self.daily_quotes.sync_trade_date_from_tushare(
                    resolved_token,
                    trade_date,
                    pro_client=pro_client,
                )
        except Exception as exc:
            self.logger.info("daily_quotes_unavailable trade_date=%s error=%s", trade_date, exc)
        return self.daily_quotes.load_quotes(trade_date, ts_codes=ts_codes)

    def has_daily_quote_cache(self, trade_date: str) -> bool:
        return self.daily_quotes.has_trade_date(trade_date)

    def cached_daily_quotes(self, trade_date: str, *, ts_codes: list[str] | None = None) -> dict[str, DailyQuote]:
        return self.daily_quotes.load_quotes(trade_date, ts_codes=ts_codes)

    def cache_daily_quote_rows(
        self,
        trade_date: str,
        rows: list[dict[str, object]],
        *,
        ts_codes: list[str] | None = None,
    ) -> dict[str, DailyQuote]:
        self.daily_quotes.upsert_daily_quotes(rows, updated_at=datetime.now().strftime("%Y%m%d%H%M%S"))
        return self.daily_quotes.load_quotes(trade_date, ts_codes=ts_codes)

    def _create_or_open_from_path(self, ptrade_json_path: Path, *, overwrite: bool) -> SessionDraft:
        imported = parse_ptrade_json(ptrade_json_path, self.stock_matcher)
        overwrite = overwrite or self._blank_draft_can_be_replaced(imported.manage_date, raise_on_edited=False)
        return self._create_or_open_imported(imported, ptrade_json_path, overwrite=overwrite)

    def _create_or_open_imported(
        self,
        imported: ImportedPtradeData,
        ptrade_json_path: Path,
        *,
        overwrite: bool,
    ) -> SessionDraft:
        self.logger.info("ptrade_imported path=%s manage_date=%s holdings=%s overwrite=%s", ptrade_json_path, imported.manage_date, len(imported.holdings), overwrite)
        previous_day = self.calendar.previous_trade_day(imported.manage_date)
        expected_trade_date = self.calendar.next_trade_day(imported.manage_date)
        previous_order_path = None
        if previous_day and self.config.order_data_dir:
            previous_order_path = Path(self.config.order_data_dir) / f"{previous_day}.json"
        export_json_path = self._export_json_path(imported.manage_date)
        return self._with_read_only_state(self.drafts.create_draft(
            imported,
            expected_trade_date=expected_trade_date,
            ptrade_json_path=str(ptrade_json_path),
            export_json_path=export_json_path,
            previous_order_path=previous_order_path,
            overwrite=overwrite,
        ))

    def _blank_draft_can_be_replaced(self, manage_date: str, *, raise_on_edited: bool) -> bool:
        try:
            draft = self.drafts.load_draft(manage_date)
        except KeyError:
            return False
        if draft.ptrade_json_path:
            return False
        if draft.stocks:
            if raise_on_edited:
                raise ValueError("当前日期已有手动草稿，请先删除历史数据后再导入")
            return False
        return True

    def _create_or_open_blank(self, manage_date: str) -> SessionDraft:
        imported = ImportedPtradeData(manage_date=manage_date, fund=self._empty_fund(), holdings=[])
        export_json_path = self._export_json_path(manage_date)
        self.logger.info("blank_draft_opened manage_date=%s", manage_date)
        return self._with_read_only_state(self.drafts.create_draft(
            imported,
            expected_trade_date=self.calendar.next_trade_day(manage_date),
            ptrade_json_path="",
            export_json_path=export_json_path,
            overwrite=False,
        ))

    def _empty_draft(self, manage_date: str, *, export_state: str = "draft") -> SessionDraft:
        export_json_path = self._export_json_path(manage_date)
        return SessionDraft(
            manage_date=manage_date,
            expected_trade_date=self.calendar.next_trade_day(manage_date),
            fund=self._empty_fund(),
            stocks=[],
            ptrade_json_path="",
            export_json_path=export_json_path,
            export_state=export_state,
            read_only=self._manage_date_is_read_only(manage_date) if export_state == "empty" else False,
        )

    def _export_json_path(self, manage_date: str) -> str:
        if not self.config.order_data_dir:
            return ""
        return str(Path(self.config.order_data_dir) / f"{manage_date}.json")

    def _empty_fund(self) -> FundSnapshot:
        return FundSnapshot(
            cash=Decimal("0"),
            positions_value=Decimal("0"),
            portfolio_value=Decimal("0"),
            stock_positions_value=Decimal("0"),
            calibrated_cash=Decimal("0"),
        )

    def _manage_date_for_order(self, order_id: int) -> str:
        row = self.conn.execute("select manage_date from orders where id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError(f"Order not found: {order_id}")
        return str(row["manage_date"])

    def current_editable_manage_date(self, *, today: str | None = None, now: datetime | None = None) -> str:
        today = today or self._today(now)
        if self.calendar.is_trade_day(today):
            current_time = (now or self._now()).time()
            if current_time > CURRENT_TRADE_DAY_CUTOFF:
                return today
            return self.calendar.previous_trade_day(today) or today
        return self.calendar.latest_trade_day_on_or_before(today) or today

    def _earliest_ptrade_json_date(self) -> str:
        path = find_earliest_ptrade_json(self.config.ptrade_data_dir)
        return path.stem if path else ""

    def _manage_date_range_start(self, *, today: str, latest_trade_date: str) -> str:
        earliest_ptrade_date = self._earliest_ptrade_json_date()
        if earliest_ptrade_date:
            return self.calendar.previous_trade_day(earliest_ptrade_date) or earliest_ptrade_date
        if self.calendar.is_trade_day(today):
            return self.calendar.previous_trade_day(today) or today
        return latest_trade_date

    def _calendar_sync_start_date(self, today: str) -> str:
        earliest_ptrade_date = self._earliest_ptrade_json_date()
        if earliest_ptrade_date:
            return self._calendar_lookback_start(earliest_ptrade_date)
        return self._calendar_lookback_start(today)

    def _calendar_lookback_start(self, today: str) -> str:
        return (datetime.strptime(today, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")

    def _today(self, now: datetime | None = None) -> str:
        return (now or self._now()).strftime("%Y%m%d")

    def _now(self) -> datetime:
        return self._now_provider()

    def _with_read_only_state(
        self,
        draft: SessionDraft,
        *,
        today: str | None = None,
        now: datetime | None = None,
    ) -> SessionDraft:
        draft.read_only = self._manage_date_is_read_only(draft.manage_date, today=today, now=now)
        return draft

    def _manage_date_is_read_only(
        self,
        manage_date: str,
        *,
        today: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        return manage_date < self.current_editable_manage_date(today=today, now=now)

    def _ptrade_data_differs(self, imported: ImportedPtradeData, draft: SessionDraft) -> bool:
        return self._fund_key(imported.fund) != self._fund_key(draft.fund) or self._holdings_key(imported.holdings) != self._draft_holdings_key(draft)

    def _fund_key(self, fund: FundSnapshot) -> tuple[str, str, str, str, str]:
        return (
            _decimal_key(fund.cash),
            _decimal_key(fund.positions_value),
            _decimal_key(fund.portfolio_value),
            _decimal_key(fund.stock_positions_value),
            _decimal_key(fund.calibrated_cash),
        )

    def _holdings_key(self, holdings: list[Holding]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            sorted(
                (
                    holding.ts_code,
                    holding.stock_code,
                    holding.stock_name,
                    holding.current_amount,
                    holding.enable_amount,
                    _decimal_key(holding.last_price),
                    _decimal_key(holding.cost_price),
                    _decimal_key(holding.market_value),
                    _decimal_key(holding.profit_ratio),
                    _decimal_key(holding.income_balance),
                    holding.is_stock,
                )
                for holding in holdings
            )
        )

    def _draft_holdings_key(self, draft: SessionDraft) -> tuple[tuple[object, ...], ...]:
        return self._holdings_key([stock.holding for stock in draft.stocks if stock.holding])

    def _order_data_differs(self, order_data: dict[str, dict[str, Any]], draft: SessionDraft) -> bool:
        return self._order_data_key(order_data) != self._order_data_key(build_order_json(draft))

    def _load_order_json(self, path: Path) -> dict[str, dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Order JSON root must be an object")
        result: dict[str, dict[str, Any]] = {}
        for raw_ts_code, raw_stock_data in data.items():
            if not isinstance(raw_stock_data, dict):
                continue
            ts_code = str(raw_ts_code)
            stock_name = str(raw_stock_data.get("stock_name") or ts_code)
            orders_by_type: dict[str, list[dict[str, object]]] = {}
            for order_type in ORDER_TYPES:
                raw_orders = raw_stock_data.get(order_type, [])
                if not isinstance(raw_orders, list):
                    continue
                for raw_order in raw_orders:
                    if not isinstance(raw_order, dict) or "price" not in raw_order or "shares" not in raw_order:
                        continue
                    orders_by_type.setdefault(order_type, []).append(
                        {
                            "price": Decimal(str(raw_order["price"])),
                            "shares": int(Decimal(str(raw_order["shares"]))),
                        }
                    )
            result[ts_code] = {"stock_name": stock_name, "orders": orders_by_type}
        return result

    def _order_data_key(self, order_data: dict[str, dict[str, Any]]) -> tuple[tuple[object, ...], ...]:
        rows = []
        for ts_code, stock_data in order_data.items():
            stock_name = str(stock_data.get("stock_name") or ts_code)
            orders_by_type = stock_data.get("orders")
            if orders_by_type is None:
                orders_by_type = {
                    order_type: stock_data.get(order_type, [])
                    for order_type in ORDER_TYPES
                    if stock_data.get(order_type)
                }
            order_rows = []
            for order_type in ORDER_TYPES:
                for order in orders_by_type.get(order_type, []):
                    order_rows.append((order_type, _decimal_key(order["price"]), int(order["shares"])))
            if order_rows:
                rows.append((ts_code, stock_name, tuple(order_rows)))
        return tuple(sorted(rows))


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


def find_ptrade_json_for_date(ptrade_data_dir: str, manage_date: str) -> Path | None:
    if not ptrade_data_dir:
        return None
    path = Path(ptrade_data_dir) / f"{manage_date}.json"
    if path.is_file() and PTRADER_JSON_RE.match(path.name):
        return path
    return None


def find_order_json_for_date(order_data_dir: str, manage_date: str) -> Path | None:
    if not order_data_dir:
        return None
    path = Path(order_data_dir) / f"{manage_date}.json"
    if path.is_file() and PTRADER_JSON_RE.match(path.name):
        return path
    return None


def find_earliest_ptrade_json(ptrade_data_dir: str) -> Path | None:
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
    return min(candidates, key=lambda path: path.stem)


def _decimal_key(value: Decimal | int | float | str) -> str:
    decimal_value = Decimal(str(value))
    normalized = decimal_value.normalize()
    if normalized == normalized.to_integral_value():
        return format(normalized.quantize(Decimal("1")), "f")
    return format(normalized, "f")
