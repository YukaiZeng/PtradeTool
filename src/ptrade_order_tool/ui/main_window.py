from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import get_user_data_dir, save_config
from ptrade_order_tool.data.stock_master import MissingTushareToken, load_tushare_token, save_tushare_token
from ptrade_order_tool.models import SessionDraft
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.settings_dialog import SettingsDialog
from ptrade_order_tool.ui.stock_card import StockCard


class StockUpdateWorker(QThread):
    finishedWithResult = Signal(int)
    failedWithMessage = Signal(str)

    def __init__(self, service: AppService, today: str, executable_dir: Path, user_data_dir: Path) -> None:
        super().__init__()
        self.service = service
        self.today = today
        self.executable_dir = executable_dir
        self.user_data_dir = user_data_dir

    def run(self) -> None:
        try:
            count = self.service.update_stock_basic(
                today=self.today,
                executable_dir=self.executable_dir,
                user_data_dir=self.user_data_dir,
            )
        except MissingTushareToken as exc:
            self.failedWithMessage.emit(str(exc))
        except Exception as exc:
            self.failedWithMessage.emit(f"股票基础数据更新失败: {exc}")
        else:
            self.finishedWithResult.emit(count)


class MainWindow(QMainWindow):
    def __init__(
        self,
        draft: SessionDraft | None = None,
        service: AppService | None = None,
        *,
        auto_update_stock_basic: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Ptrade Order Tool")
        self.setMinimumSize(1100, 720)
        self.draft = draft
        self.service = service
        self._last_deleted_snapshot = None
        self._stock_update_worker: StockUpdateWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.account_bar = QWidget()
        account_layout = QHBoxLayout(self.account_bar)
        account_layout.setContentsMargins(0, 0, 0, 0)
        account_layout.setSpacing(8)
        self.date_combo = QComboBox()
        self.date_combo.setObjectName("manage_date_combo")
        self.date_combo.currentTextChanged.connect(self._handle_date_changed)
        self.date_combo.setMinimumWidth(118)
        self.settings_button = QPushButton("设置目录")
        self.settings_button.setObjectName("settings_button")
        self.settings_button.clicked.connect(self._handle_settings)
        self.manual_import_button = QPushButton("手动导入")
        self.manual_import_button.setObjectName("manual_import_button")
        self.manual_import_button.clicked.connect(self._handle_manual_import)
        self.reimport_button = QPushButton("重新导入")
        self.reimport_button.setObjectName("reimport_button")
        self.reimport_button.clicked.connect(self._handle_reimport)
        self.total_label = QLabel("总额 --")
        self.total_label.setObjectName("account_total_label")
        self.stock_value_label = QLabel("股票市值 --")
        self.stock_value_label.setObjectName("account_stock_value_label")
        self.cash_label = QLabel("可用余额 --")
        self.cash_label.setObjectName("account_cash_label")
        self.opening_amount_label = QLabel("开仓金额 --")
        self.opening_amount_label.setObjectName("account_opening_amount_label")
        self.opening_amount_label.hide()
        self.draft_summary_label = QLabel("股票 -- | 待确认 --")
        self.draft_summary_label.setObjectName("draft_summary_label")
        self.stock_update_button = QPushButton("生成股票基础数据")
        self.stock_update_button.setObjectName("stock_update_button")
        self.stock_update_button.clicked.connect(self._handle_stock_update)
        self.stock_search_input = QLineEdit()
        self.stock_search_input.setObjectName("stock_search_input")
        self.stock_search_input.setPlaceholderText("输入股票代码、名称、拼音")
        self.stock_search_input.returnPressed.connect(self._handle_add_stock)
        self.add_stock_button = QPushButton("添加股票")
        self.add_stock_button.setObjectName("add_stock_button")
        self.add_stock_button.clicked.connect(self._handle_add_stock)
        self.open_export_dir_button = QPushButton("打开导出目录")
        self.open_export_dir_button.setObjectName("open_export_dir_button")
        self.open_export_dir_button.clicked.connect(self._handle_open_export_dir)
        self.open_export_dir_button.hide()
        self.check_export_button = QPushButton("导出检查")
        self.check_export_button.setObjectName("check_export_button")
        self.check_export_button.clicked.connect(self._handle_check_export)
        self.export_button = QPushButton("导出订单 JSON")
        self.export_button.setObjectName("export_button")
        self.export_button.clicked.connect(self._handle_export)
        self.undo_delete_button = QPushButton("撤销删除")
        self.undo_delete_button.setObjectName("undo_delete_button")
        self.undo_delete_button.hide()
        self.undo_delete_button.clicked.connect(self._handle_undo_delete)
        self.locate_unconfirmed_button = QPushButton("定位未确认")
        self.locate_unconfirmed_button.setObjectName("locate_unconfirmed_button")
        self.locate_unconfirmed_button.hide()
        self.locate_unconfirmed_button.clicked.connect(self._handle_locate_unconfirmed)
        self.status_label = QLabel("")
        self.status_label.setObjectName("startup_status_label")

        account_layout.addWidget(self.date_combo)
        account_layout.addWidget(self.total_label)
        account_layout.addWidget(self.stock_value_label)
        account_layout.addWidget(self.cash_label)
        account_layout.addWidget(self.opening_amount_label)
        account_layout.addWidget(self.draft_summary_label)
        account_layout.addWidget(self.status_label)
        account_layout.addStretch(1)
        layout.addWidget(self.account_bar)

        self.action_bar = QWidget()
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        self.stock_search_input.setMinimumWidth(260)
        action_layout.addWidget(self.settings_button)
        action_layout.addWidget(self.manual_import_button)
        action_layout.addWidget(self.reimport_button)
        action_layout.addWidget(self.stock_update_button)
        action_layout.addWidget(self.undo_delete_button)
        action_layout.addWidget(self.locate_unconfirmed_button)
        action_layout.addStretch(1)
        action_layout.addWidget(self.stock_search_input)
        action_layout.addWidget(self.add_stock_button)
        action_layout.addWidget(self.open_export_dir_button)
        action_layout.addWidget(self.check_export_button)
        action_layout.addWidget(self.export_button)
        layout.addWidget(self.action_bar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("stock_filter_tabs")
        self.stock_scroll, self.stock_content, self.stock_layout = self._make_scroll_tab()
        self.tabs.addTab(QWidget(), "全部")
        self.tabs.addTab(QWidget(), "开仓")
        self.tabs.addTab(QWidget(), "持仓")
        self.tabs.currentChanged.connect(lambda index: self._apply_stock_filter())
        layout.addWidget(self.tabs)
        layout.addWidget(self.stock_scroll)

        if draft:
            self.set_draft(draft)
        else:
            self._render_empty_state()
        self.refresh_stock_update_button()
        self.refresh_date_combo()
        if auto_update_stock_basic:
            self.start_stock_basic_update_if_needed()

    def set_startup_message(self, message: str) -> None:
        self.status_label.setText(message)

    def refresh_stock_update_button(self) -> None:
        if not self.service:
            self.set_stock_update_state("generate")
            return
        today = datetime.now().strftime("%Y%m%d")
        self.set_stock_update_state(self.service.stock_update_button_state(today))

    def set_stock_update_state(self, state: str) -> None:
        if state == "generate":
            self.stock_update_button.setText("生成股票基础数据")
            self.stock_update_button.setEnabled(True)
        elif state == "updated_disabled":
            self.stock_update_button.setText("已更新股票基础数据")
            self.stock_update_button.setEnabled(False)
        elif state == "update_disabled_non_trade_day":
            self.stock_update_button.setText("更新股票基础数据")
            self.stock_update_button.setEnabled(False)
        else:
            self.stock_update_button.setText("更新股票基础数据")
            self.stock_update_button.setEnabled(True)

    def start_stock_basic_update_if_needed(self) -> None:
        if not self.service:
            return
        stock_matcher = getattr(self.service, "stock_matcher", None)
        if stock_matcher is not None and not hasattr(stock_matcher, "sync_from_tushare"):
            return
        today = datetime.now().strftime("%Y%m%d")
        if self.service.stock_update_button_state(today) not in {"generate", "update_enabled"}:
            return
        if self._stock_update_worker and self._stock_update_worker.isRunning():
            return
        self.stock_update_button.setEnabled(False)
        self.status_label.setText("正在更新股票基础数据...")
        self._stock_update_worker = StockUpdateWorker(self.service, today, Path.cwd(), get_user_data_dir())
        self._stock_update_worker.finishedWithResult.connect(self._handle_stock_update_finished)
        self._stock_update_worker.failedWithMessage.connect(self._handle_stock_update_failed)
        self._stock_update_worker.finished.connect(self.refresh_stock_update_button)
        self._stock_update_worker.start()

    def refresh_date_combo(self) -> None:
        self.date_combo.blockSignals(True)
        self.date_combo.clear()
        dates = self.service.list_manage_dates() if self.service else []
        if not dates and self.draft:
            dates = [self.draft.manage_date]
        self.date_combo.addItems(dates)
        if self.draft:
            index = self.date_combo.findText(self.draft.manage_date)
            if index >= 0:
                self.date_combo.setCurrentIndex(index)
                self.date_combo.setItemData(index, self._date_combo_text(self.draft), Qt.DisplayRole)
        self.date_combo.blockSignals(False)

    def set_draft(self, draft: SessionDraft) -> None:
        self.draft = draft
        self.total_label.setText(f"总额 {self._format_money(draft.fund.portfolio_value)}")
        self.stock_value_label.setText(f"股票市值 {self._format_money(draft.fund.stock_positions_value)}")
        opening_amount = self._opening_order_amount(draft)
        if opening_amount:
            self.opening_amount_label.setText(f"开仓金额 {self._format_money(opening_amount)}")
            self.opening_amount_label.show()
        else:
            self.opening_amount_label.hide()
        self.cash_label.setText(f"可用余额 {self._format_money(draft.fund.calibrated_cash)}")
        self._refresh_draft_summary()
        self.refresh_date_combo()

        self._clear_layout(self.stock_layout)

        for stock in draft.stocks:
            self.stock_layout.addWidget(self._make_stock_card(stock))

        self.stock_layout.addStretch(1)

        self._refresh_tab_titles()
        self._apply_stock_filter()
        self._apply_read_only_state()
        self.open_export_dir_button.setVisible(bool(draft.export_json_path))
        self._refresh_locate_unconfirmed_button()

    def _render_empty_state(self) -> None:
        self.opening_amount_label.hide()
        self.draft_summary_label.setText("股票 -- | 待确认 --")
        self.tabs.setTabText(0, "全部")
        self.tabs.setTabText(1, "开仓")
        self.tabs.setTabText(2, "持仓")
        self._clear_layout(self.stock_layout)
        empty_label = QLabel("未打开盘后数据。请先设置 PTrade 盘后目录，或点击“手动导入”。")
        empty_label.setObjectName("empty_state_label")
        self.stock_layout.addWidget(empty_label)
        self.stock_layout.addStretch(1)

    def _refresh_draft_summary(self) -> None:
        if not self.draft:
            self.draft_summary_label.setText("股票 -- | 待确认 --")
            return
        total = len(self.draft.stocks)
        unconfirmed = sum(1 for stock in self.draft.stocks for order in stock.orders if not order.confirmed)
        state_text = {
            "draft": "草稿",
            "exported": "已导出",
            "modified_after_export": "导出后修改",
        }.get(self.draft.export_state, self.draft.export_state)
        self.draft_summary_label.setText(f"股票 {total} | 待确认 {unconfirmed} | {state_text}")
        self._refresh_locate_unconfirmed_button()

    def _refresh_locate_unconfirmed_button(self) -> None:
        if not hasattr(self, "locate_unconfirmed_button"):
            return
        has_unconfirmed = bool(
            self.draft and any(not order.confirmed for stock in self.draft.stocks for order in stock.orders)
        )
        self.locate_unconfirmed_button.setVisible(has_unconfirmed)

    def _date_combo_text(self, draft: SessionDraft) -> str:
        suffix = " 只读" if draft.read_only else ""
        return f"{draft.manage_date}{suffix}"

    def _opening_order_amount(self, draft: SessionDraft) -> Decimal:
        total = Decimal("0")
        for stock in draft.stocks:
            for order in stock.orders:
                if order.order_type in {"buy_stop", "buy_limit"}:
                    total += order.price * Decimal(order.shares)
        return total

    def _format_money(self, value: Decimal) -> str:
        return f"{value:,.2f}"

    def _refresh_tab_titles(self) -> None:
        if not self.draft:
            return
        total = len(self.draft.stocks)
        holding = sum(1 for stock in self.draft.stocks if stock.is_holding)
        opening = total - holding
        self.tabs.setTabText(0, f"全部 {total}")
        self.tabs.setTabText(1, f"开仓 {opening}")
        self.tabs.setTabText(2, f"持仓 {holding}")

    def _apply_stock_filter(self) -> None:
        if not hasattr(self, "stock_content"):
            return
        filter_index = self.tabs.currentIndex()
        for card in self.stock_content.findChildren(StockCard):
            if filter_index == 1:
                card.setVisible(not card.stock.is_holding)
            elif filter_index == 2:
                card.setVisible(card.stock.is_holding)
            else:
                card.setVisible(True)

    def _make_scroll_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        tab_layout = QVBoxLayout(content)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(10)
        scroll.setWidget(content)
        return scroll, content, tab_layout

    def _make_stock_card(self, stock):
        card = StockCard(stock, read_only=bool(self.draft and self.draft.read_only))
        card.confirmRequested.connect(self._handle_order_confirm)
        card.deleteRequested.connect(self._handle_order_delete)
        card.orderChanged.connect(self._handle_order_change)
        card.orderTypeChanged.connect(self._handle_order_type_change)
        card.addOrderRequested.connect(self._handle_add_order)
        return card

    def _apply_read_only_state(self) -> None:
        read_only = bool(self.draft and self.draft.read_only)
        self.stock_search_input.setEnabled(not read_only)
        self.add_stock_button.setEnabled(not read_only)
        self.reimport_button.setEnabled(not read_only)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _handle_order_confirm(self, row: OrderRow) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not row.order.id:
            self.status_label.setText("订单服务未就绪")
            return
        self.draft = self.service.update_and_confirm_order(
            row.order.id,
            price=row.selected_price(),
            shares=row.selected_shares(),
            order_type=row.selected_order_type(),
        )
        self.status_label.setText("订单已确认")
        self.set_draft(self.draft)

    def _handle_order_change(self, row: OrderRow) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not row.order.id:
            self.status_label.setText("订单服务未就绪")
            return
        self.draft = self.service.update_order_change(
            row.order.id,
            price=row.selected_price(),
            shares=row.selected_shares(),
            order_type=row.selected_order_type(),
        )
        self._refresh_draft_summary()
        opening_amount = self._opening_order_amount(self.draft)
        if opening_amount:
            self.opening_amount_label.setText(f"开仓金额 {self._format_money(opening_amount)}")
            self.opening_amount_label.show()
        else:
            self.opening_amount_label.hide()
        self.status_label.setText("订单已修改，需重新确认")

    def _handle_order_type_change(self, row: OrderRow) -> None:
        self._handle_order_change(row)
        if self.draft:
            self.set_draft(self.draft)

    def _handle_order_delete(self, row: OrderRow) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not row.order.id:
            self.status_label.setText("订单服务未就绪")
            return
        self.draft, self._last_deleted_snapshot = self.service.delete_order_with_snapshot(row.order.id)
        self.status_label.setText("订单已删除")
        self.set_draft(self.draft)
        self.undo_delete_button.show()

    def _handle_add_order(self, stock, order_type: str) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not self.draft:
            self.status_label.setText("订单服务未就绪")
            return
        self.draft = self.service.add_order(
            self.draft.manage_date,
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            order_type=order_type,
        )
        self.status_label.setText("已新增订单，需确认")
        self.set_draft(self.draft)

    def _handle_add_stock(self) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not self.draft:
            self.status_label.setText("订单服务未就绪")
            return
        query = self.stock_search_input.text().strip()
        if not query:
            self.status_label.setText("请输入股票代码或名称")
            return
        try:
            candidates = self.service.search_manual_stock_candidates(query, limit=20)
            if not candidates:
                raise ValueError(f"未找到股票: {query}")
            if len(candidates) == 1:
                stock = candidates[0]
            else:
                stock = self._select_stock_candidate(candidates)
                if not stock:
                    self.status_label.setText("已取消添加股票")
                    return
            self.draft = self.service.add_manual_stock_by_code(
                self.draft.manage_date,
                stock["ts_code"],
                stock_name=stock["name"],
            )
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText("已添加股票")
        self.stock_search_input.clear()
        self.set_draft(self.draft)

    def _select_stock_candidate(self, candidates: list[dict[str, str]]) -> dict[str, str] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("选择股票")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        list_widget.setObjectName("stock_candidate_list")
        for stock in candidates:
            item = QListWidgetItem(f"{stock['ts_code']}  {stock['name']}")
            item.setData(Qt.UserRole, stock)
            list_widget.addItem(item)
        if list_widget.count():
            list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)
        buttons = QHBoxLayout()
        cancel_button = QPushButton("取消")
        ok_button = QPushButton("添加")
        ok_button.setObjectName("stock_candidate_confirm_button")
        cancel_button.clicked.connect(dialog.reject)
        ok_button.clicked.connect(dialog.accept)
        list_widget.itemDoubleClicked.connect(lambda item: dialog.accept())
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(ok_button)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.Accepted or not list_widget.currentItem():
            return None
        return list_widget.currentItem().data(Qt.UserRole)

    def _handle_date_changed(self, manage_date: str) -> None:
        manage_date = manage_date.split()[0]
        if not manage_date or not self.service:
            return
        self.draft = self.service.load_draft(manage_date)
        self.status_label.setText("历史日期只读，可重新导出" if self.draft.read_only else "已切换管理日期")
        self.set_draft(self.draft)

    def _handle_settings(self) -> None:
        if not self.service:
            self.status_label.setText("配置服务未就绪")
            return
        user_data_dir = get_user_data_dir()
        token_hint = self._tushare_token_hint(user_data_dir)
        dialog = SettingsDialog(self.service.config, self, token_hint=token_hint)
        if dialog.exec() != QDialog.Accepted:
            return
        config = dialog.to_config(self.service.config)
        save_config(config, user_data_dir)
        if dialog.token_text():
            try:
                save_tushare_token(user_data_dir, dialog.token_text())
            except ValueError as exc:
                self.status_label.setText(str(exc))
                return
        self.service.update_config(config)
        self.status_label.setText("目录设置已保存")

    def _tushare_token_hint(self, user_data_dir: Path) -> str:
        try:
            token = load_tushare_token(Path.cwd(), user_data_dir)
        except MissingTushareToken:
            return "留空表示不修改 TUSHARE_TOKEN"
        if len(token) <= 8:
            masked = "*" * len(token)
        else:
            masked = f"{token[:4]}...{token[-4:]}"
        return f"当前: {masked}，留空表示不修改"

    def _handle_manual_import(self) -> None:
        if not self.service:
            self.status_label.setText("导入服务未就绪")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Ptrade 盘后 JSON",
            self.service.config.ptrade_data_dir,
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            self.draft = self.service.import_ptrade_json(Path(path))
        except Exception as exc:
            self.status_label.setText(f"导入失败: {exc}")
            return
        self.status_label.setText("导入完成")
        self.set_draft(self.draft)

    def _handle_reimport(self) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not self.draft:
            self.status_label.setText("没有可重新导入的草稿")
            return
        reply = QMessageBox.question(
            self,
            "重新导入当前日期",
            "重新导入会覆盖当前日期草稿，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.status_label.setText("已取消重新导入")
            return
        try:
            self.draft = self.service.reimport_current_draft(self.draft.manage_date)
        except Exception as exc:
            self.status_label.setText(f"重新导入失败: {exc}")
            return
        self.status_label.setText("重新导入完成")
        self.set_draft(self.draft)

    def _handle_stock_update(self) -> None:
        if not self.service:
            self.status_label.setText("股票基础数据服务未就绪")
            return
        today = datetime.now().strftime("%Y%m%d")
        try:
            count = self.service.update_stock_basic(
                today=today,
                executable_dir=Path.cwd(),
                user_data_dir=get_user_data_dir(),
            )
        except MissingTushareToken as exc:
            self.status_label.setText(str(exc))
            return
        except Exception as exc:
            self.status_label.setText(f"股票基础数据更新失败: {exc}")
            return
        self.status_label.setText(f"股票基础数据已更新: {count} 条")
        self.refresh_stock_update_button()

    def _handle_stock_update_finished(self, count: int) -> None:
        self.status_label.setText(f"股票基础数据已更新: {count} 条")

    def _handle_stock_update_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def _handle_undo_delete(self) -> None:
        if not self.service or not self._last_deleted_snapshot:
            return
        self.draft = self.service.restore_deleted_order(self._last_deleted_snapshot)
        self._last_deleted_snapshot = None
        self.undo_delete_button.hide()
        self.status_label.setText("已撤销删除")
        self.set_draft(self.draft)

    def _handle_locate_unconfirmed(self) -> None:
        if not self.draft:
            return
        stock = next(
            (
                stock
                for stock in self.draft.stocks
                if any(not order.confirmed for order in stock.orders)
            ),
            None,
        )
        if not stock:
            self.status_label.setText("没有待确认订单")
            self._refresh_locate_unconfirmed_button()
            return
        self.tabs.setCurrentIndex(0)
        card = next(
            (card for card in self.stock_content.findChildren(StockCard) if card.stock.ts_code == stock.ts_code),
            None,
        )
        if card:
            self.stock_scroll.ensureWidgetVisible(card)
        self.status_label.setText(f"已定位待确认: {stock.ts_code} {stock.stock_name}")

    def _handle_open_export_dir(self) -> None:
        if not self.draft or not self.draft.export_json_path:
            self.status_label.setText("导出路径未配置")
            return
        directory = Path(self.draft.export_json_path).parent
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        self.status_label.setText(f"已打开导出目录: {directory}")

    def _handle_check_export(self) -> None:
        if not self.service or not self.draft:
            self.status_label.setText("没有可检查的草稿")
            return
        validation = self.service.validate_draft_for_export(self.draft.manage_date)
        pending = self._pending_order_lines(self.draft)
        self._show_export_check_dialog(pending, validation.blockers, validation.warnings)
        if validation.blockers:
            self.status_label.setText(f"导出检查: {len(validation.blockers)} 个阻断项")
        elif validation.warnings:
            self.status_label.setText(f"导出检查: {len(validation.warnings)} 个提醒项")
        else:
            self.status_label.setText("导出检查通过")

    def _pending_order_lines(self, draft: SessionDraft) -> list[str]:
        lines = []
        for stock in draft.stocks:
            pending_count = sum(1 for order in stock.orders if not order.confirmed)
            if pending_count:
                lines.append(f"{stock.ts_code} {stock.stock_name} 待确认 {pending_count} 条")
        return lines

    def _show_export_check_dialog(self, pending: list[str], blockers: list[str], warnings: list[str]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("导出检查")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        if blockers:
            summary_text = f"需要处理 {len(blockers)} 项后才能导出"
        elif warnings:
            summary_text = f"有 {len(warnings)} 项建议复核，可继续导出"
        else:
            summary_text = "检查通过，可以导出"
        summary = QLabel(summary_text)
        summary.setObjectName("export_check_summary")
        layout.addWidget(summary)
        layout.addWidget(self._make_export_check_section("待确认", pending, "pending"))
        layout.addWidget(self._make_export_check_section("阻断项", blockers, "blocker"))
        layout.addWidget(self._make_export_check_section("提醒项", warnings, "warning"))
        buttons = QHBoxLayout()
        locate_button = QPushButton("定位未确认")
        close_button = QPushButton("关闭")
        locate_button.setEnabled(bool(pending))
        locate_button.clicked.connect(lambda: (dialog.accept(), self._handle_locate_unconfirmed()))
        close_button.clicked.connect(dialog.accept)
        buttons.addStretch(1)
        buttons.addWidget(locate_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        dialog.exec()

    def _make_export_check_section(self, title: str, items: list[str], tone: str) -> QWidget:
        section = QWidget()
        section.setObjectName("export_check_section")
        section.setProperty("tone", tone)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title_label = QLabel(f"{title} {len(items)} 项")
        title_label.setObjectName("export_check_section_title")
        layout.addWidget(title_label)
        if items:
            for item in items:
                item_label = QLabel(item)
                item_label.setObjectName("export_check_item")
                item_label.setWordWrap(True)
                layout.addWidget(item_label)
        else:
            empty_label = QLabel("无")
            empty_label.setObjectName("export_check_item")
            layout.addWidget(empty_label)
        return section

    def _handle_export(self) -> None:
        if not self.service or not self.draft:
            self.status_label.setText("没有可导出的草稿")
            return
        validation = self.service.validate_draft_for_export(self.draft.manage_date)
        if validation.blockers:
            QMessageBox.warning(self, "无法导出", self._format_export_validation(validation.blockers, []))
            self.status_label.setText(validation.blockers[0])
            return
        if validation.warnings:
            reply = QMessageBox.question(
                self,
                "导出提醒",
                self._format_export_validation([], validation.warnings) + "\n\n是否继续导出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.status_label.setText("已取消导出")
                return
        try:
            validation = self.service.export_draft(self.draft.manage_date)
        except FileExistsError:
            reply = QMessageBox.question(
                self,
                "覆盖订单 JSON",
                "订单 JSON 已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.status_label.setText("已取消覆盖")
                return
            validation = self.service.export_draft(self.draft.manage_date, allow_overwrite=True)
        if not validation.can_export:
            self.status_label.setText(validation.blockers[0])
            return
        self._finish_export_success()

    def _format_export_validation(self, blockers: list[str], warnings: list[str]) -> str:
        lines = []
        if blockers:
            lines.append(f"阻断项 {len(blockers)} 个：")
            lines.extend(f"- {item}" for item in blockers)
        if warnings:
            if lines:
                lines.append("")
            lines.append(f"提醒项 {len(warnings)} 个：")
            lines.extend(f"- {item}" for item in warnings)
        return "\n".join(lines)

    def _finish_export_success(self) -> None:
        if not self.service or not self.draft:
            return
        self.draft = self.service.load_draft(self.draft.manage_date)
        self.status_label.setText(f"导出完成: {self.draft.export_json_path}")
        self.set_draft(self.draft)
