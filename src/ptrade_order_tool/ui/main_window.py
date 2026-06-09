from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.draft_summary_label = QLabel("股票 -- | 待确认 --")
        self.draft_summary_label.setObjectName("draft_summary_label")
        self.stock_update_button = QPushButton("生成股票基础数据")
        self.stock_update_button.setObjectName("stock_update_button")
        self.stock_update_button.clicked.connect(self._handle_stock_update)
        self.stock_search_input = QLineEdit()
        self.stock_search_input.setObjectName("stock_search_input")
        self.stock_search_input.setPlaceholderText("输入股票代码、名称、拼音")
        self.add_stock_button = QPushButton("添加股票")
        self.add_stock_button.setObjectName("add_stock_button")
        self.add_stock_button.clicked.connect(self._handle_add_stock)
        self.export_button = QPushButton("导出订单 JSON")
        self.export_button.setObjectName("export_button")
        self.export_button.clicked.connect(self._handle_export)
        self.undo_delete_button = QPushButton("撤销删除")
        self.undo_delete_button.setObjectName("undo_delete_button")
        self.undo_delete_button.hide()
        self.undo_delete_button.clicked.connect(self._handle_undo_delete)
        self.status_label = QLabel("")
        self.status_label.setObjectName("startup_status_label")
        self.status_label.setMinimumWidth(180)

        account_layout.addWidget(self.date_combo)
        account_layout.addWidget(self.total_label)
        account_layout.addWidget(self.stock_value_label)
        account_layout.addWidget(self.cash_label)
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
        action_layout.addStretch(1)
        action_layout.addWidget(self.stock_search_input)
        action_layout.addWidget(self.add_stock_button)
        action_layout.addWidget(self.export_button)
        layout.addWidget(self.action_bar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("stock_filter_tabs")
        self.all_tab = self._make_scroll_tab()
        self.opening_tab = self._make_scroll_tab()
        self.holding_tab = self._make_scroll_tab()
        self.tabs.addTab(self.all_tab[0], "全部")
        self.tabs.addTab(self.opening_tab[0], "开仓")
        self.tabs.addTab(self.holding_tab[0], "持仓")
        layout.addWidget(self.tabs)

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
        self.date_combo.blockSignals(False)

    def set_draft(self, draft: SessionDraft) -> None:
        self.draft = draft
        self.total_label.setText(f"总额 {draft.fund.portfolio_value}")
        self.stock_value_label.setText(f"股票市值 {draft.fund.stock_positions_value}")
        self.cash_label.setText(f"可用余额 {draft.fund.calibrated_cash}")
        self._refresh_draft_summary()
        self.refresh_date_combo()

        for _, content, layout in (self.all_tab, self.opening_tab, self.holding_tab):
            self._clear_layout(layout)

        for stock in draft.stocks:
            self.all_tab[2].addWidget(self._make_stock_card(stock))
            if stock.is_holding:
                self.holding_tab[2].addWidget(self._make_stock_card(stock))
            else:
                self.opening_tab[2].addWidget(self._make_stock_card(stock))

        for _, _, tab_layout in (self.all_tab, self.opening_tab, self.holding_tab):
            tab_layout.addStretch(1)

        self._refresh_tab_titles()
        self._apply_read_only_state()

    def _render_empty_state(self) -> None:
        self.draft_summary_label.setText("股票 -- | 待确认 --")
        self.tabs.setTabText(0, "全部")
        self.tabs.setTabText(1, "开仓")
        self.tabs.setTabText(2, "持仓")
        for _, _, tab_layout in (self.all_tab, self.opening_tab, self.holding_tab):
            self._clear_layout(tab_layout)
            empty_label = QLabel("未打开盘后数据。请先设置 PTrade 盘后目录，或点击“手动导入”。")
            empty_label.setObjectName("empty_state_label")
            tab_layout.addWidget(empty_label)
            tab_layout.addStretch(1)

    def _refresh_draft_summary(self) -> None:
        if not self.draft:
            self.draft_summary_label.setText("股票 -- | 待确认 --")
            return
        total = len(self.draft.stocks)
        holding = sum(1 for stock in self.draft.stocks if stock.is_holding)
        opening = total - holding
        unconfirmed = sum(1 for stock in self.draft.stocks for order in stock.orders if not order.confirmed)
        state_text = {
            "draft": "草稿",
            "exported": "已导出",
            "modified_after_export": "导出后修改",
        }.get(self.draft.export_state, self.draft.export_state)
        self.draft_summary_label.setText(
            f"股票 {total} | 持仓 {holding} | 开仓 {opening} | 待确认 {unconfirmed} | {state_text}"
        )

    def _refresh_tab_titles(self) -> None:
        if not self.draft:
            return
        total = len(self.draft.stocks)
        holding = sum(1 for stock in self.draft.stocks if stock.is_holding)
        opening = total - holding
        self.tabs.setTabText(0, f"全部 {total}")
        self.tabs.setTabText(1, f"开仓 {opening}")
        self.tabs.setTabText(2, f"持仓 {holding}")

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
            self.draft = self.service.add_manual_stock(self.draft.manage_date, query)
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText("已添加股票")
        self.stock_search_input.clear()
        self.set_draft(self.draft)

    def _handle_date_changed(self, manage_date: str) -> None:
        if not manage_date or not self.service:
            return
        self.draft = self.service.load_draft(manage_date)
        self.status_label.setText("历史日期只读" if self.draft.read_only else "已切换管理日期")
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

    def _handle_export(self) -> None:
        if not self.service or not self.draft:
            self.status_label.setText("没有可导出的草稿")
            return
        validation = self.service.validate_draft_for_export(self.draft.manage_date)
        if validation.blockers:
            QMessageBox.warning(self, "无法导出", "\n".join(validation.blockers))
            self.status_label.setText(validation.blockers[0])
            return
        if validation.warnings:
            reply = QMessageBox.question(
                self,
                "导出提醒",
                "\n".join(validation.warnings) + "\n\n是否继续导出？",
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

    def _finish_export_success(self) -> None:
        if not self.service or not self.draft:
            return
        self.draft = self.service.load_draft(self.draft.manage_date)
        self.status_label.setText("导出完成")
        self.set_draft(self.draft)
