from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ptrade_order_tool.app_service import AppService
from ptrade_order_tool.config import get_executable_dir, get_user_data_dir, save_config
from ptrade_order_tool.data.daily_quote_store import DAILY_FIELDS
from ptrade_order_tool.data.order_exporter import validate_export
from ptrade_order_tool.data.stock_master import MissingTushareToken, load_tushare_token, save_tushare_token
from ptrade_order_tool.data.tushare_client import TushareProClient
from ptrade_order_tool.models import DailyQuote, SessionDraft
from ptrade_order_tool.ui.digit_input import DigitInput
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.settings_dialog import SettingsDialog
from ptrade_order_tool.ui.stock_card import StockCard


class RightCheckDelegate(QStyledItemDelegate):
    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self.combo = combo

    def paint(self, painter, option, index):  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)
        text_rect = option.rect.adjusted(8, 0, -28, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, index.data() or "")
        if index.row() == self.combo.currentIndex():
            check_rect = QRect(option.rect.right() - 24, option.rect.top(), 20, option.rect.height())
            painter.drawText(check_rect, Qt.AlignCenter, "✓")


class AutoWidthComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(RightCheckDelegate(self))

    def showPopup(self):  # noqa: N802
        width = self.width()
        for index in range(self.count()):
            width = max(width, self.fontMetrics().horizontalAdvance(self.itemText(index)) + 48)
        self.view().setMinimumWidth(width)
        super().showPopup()
        popup = self.view().window()
        popup.move(self.mapToGlobal(QPoint(0, self.height())))


class StockSearchLineEdit(QLineEdit):
    candidateNavigateRequested = Signal(int)
    candidateConfirmRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._candidate_navigation_enabled = False
        self._candidate_has_highlight = False

    def set_candidate_popup_visible(self, visible: bool) -> None:
        self._candidate_navigation_enabled = visible
        if not visible:
            self._candidate_has_highlight = False

    def set_candidate_has_highlight(self, has_highlight: bool) -> None:
        self._candidate_has_highlight = has_highlight

    def keyPressEvent(self, event):  # noqa: N802
        if self._candidate_navigation_enabled and event.key() in {Qt.Key_Up, Qt.Key_Down}:
            self.candidateNavigateRequested.emit(1 if event.key() == Qt.Key_Down else -1)
            self._candidate_has_highlight = True
            event.accept()
            return
        if self._candidate_navigation_enabled and self._candidate_has_highlight and event.key() in {Qt.Key_Return, Qt.Key_Enter}:
            self.candidateConfirmRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class StatusLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self._refresh_elided_text()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._refresh_elided_text()

    def _refresh_elided_text(self) -> None:
        metrics = QFontMetrics(self.font())
        available_width = max(0, self.width() - self.contentsMargins().left() - self.contentsMargins().right())
        elided = metrics.elidedText(self._full_text, Qt.ElideRight, available_width)
        super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")


class StockFilterTabs(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stock_filter_tabs")
        self._buttons: list[QPushButton] = []
        self._current_index = 0
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for index in range(3):
            button = QPushButton("")
            button.setCheckable(True)
            button.setProperty("role", "filter_tab")
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            self._buttons.append(button)
            self._group.addButton(button, index)
            layout.addWidget(button)
        self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self.setCurrentIndex)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def addTab(self, _widget: QWidget, text: str) -> None:  # noqa: N802
        index = next((i for i, button in enumerate(self._buttons) if not button.text()), len(self._buttons) - 1)
        self.setTabText(index, text)

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self._buttons[index].setText(text)

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._buttons[index].text()

    def currentIndex(self) -> int:  # noqa: N802
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index < 0 or index >= len(self._buttons):
            return
        changed = index != self._current_index
        self._current_index = index
        self._buttons[index].setChecked(True)
        if changed:
            self.currentChanged.emit(index)


class StockUpdateWorker(QThread):
    finishedWithRows = Signal(list, list)
    failedWithMessage = Signal(str)

    def __init__(self, token: str, today: str, calendar_start_date: str, calendar_end_date: str) -> None:
        super().__init__()
        self.token = token
        self.today = today
        self.calendar_start_date = calendar_start_date
        self.calendar_end_date = calendar_end_date

    def run(self) -> None:
        try:
            client = TushareProClient(self.token, timeout=5)
            calendar_rows = client.query(
                "trade_cal",
                start_date=self.calendar_start_date,
                end_date=self.calendar_end_date,
                fields="cal_date,is_open",
            )
            if self.isInterruptionRequested():
                return
            stock_rows = client.query("stock_basic", fields="ts_code,symbol,name,list_status")
        except MissingTushareToken as exc:
            self.failedWithMessage.emit(str(exc))
        except Exception as exc:
            self.failedWithMessage.emit(f"股票基础数据更新失败: {exc}")
        else:
            if not self.isInterruptionRequested():
                self.finishedWithRows.emit(calendar_rows, stock_rows)


class DailyQuotesWorker(QThread):
    finishedWithRows = Signal(str, list)

    def __init__(
        self,
        manage_date: str,
        token: str,
        ts_codes: list[str],
    ) -> None:
        super().__init__()
        self.manage_date = manage_date
        self.token = token
        self.ts_codes = ts_codes

    def run(self) -> None:
        rows: list[dict[str, object]] = []
        try:
            rows = TushareProClient(self.token, timeout=5).query("daily", trade_date=self.manage_date, fields=DAILY_FIELDS)
        except Exception:
            rows = []
        if self.isInterruptionRequested():
            return
        self.finishedWithRows.emit(self.manage_date, rows)


class MainWindow(QMainWindow):
    def __init__(
        self,
        draft: SessionDraft | None = None,
        service: AppService | None = None,
        *,
        auto_update_stock_basic: bool = True,
        auto_update_daily_quotes: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Ptrade Order Tool")
        self.setMinimumSize(640, 0)
        self._resize_to_default_screen_half()
        self.draft = draft
        self.service = service
        self._auto_update_daily_quotes = auto_update_daily_quotes
        self._last_deleted_snapshot = None
        self._stock_update_worker: StockUpdateWorker | None = None
        self._daily_quotes_worker: DailyQuotesWorker | None = None
        self._background_workers: set[QThread] = set()
        self._daily_quote_workers_by_date: dict[str, QThread] = {}
        self._stock_candidate_by_label: dict[str, dict[str, str]] = {}
        self._selected_stock_candidate: dict[str, str] | None = None
        self._suppress_candidate_popup = False
        self._daily_quotes: dict[str, DailyQuote] = {}
        self._daily_quotes_date: str | None = None
        self._order_input_widths_by_id: dict[int, tuple[int, int]] = {}
        self._stock_cards_by_code: dict[str, StockCard] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(5)

        self.account_bar = QWidget()
        self.account_bar.setObjectName("top_tool_panel")
        self.account_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_layout = QGridLayout(self.account_bar)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setHorizontalSpacing(8)
        top_layout.setVerticalSpacing(8)
        self.date_combo = AutoWidthComboBox()
        self.date_combo.setObjectName("manage_date_combo")
        self.date_combo.currentTextChanged.connect(self._handle_date_changed)
        self.date_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.date_combo.setMinimumContentsLength(11)
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("settings_button")
        self.settings_button.setToolTip("设置 PTrade 盘后目录、订单导出目录和 Tushare Token")
        self.settings_button.clicked.connect(self._handle_settings)
        self.manual_import_button = QPushButton("导入")
        self.manual_import_button.setObjectName("manual_import_button")
        self.manual_import_button.setToolTip("手动导入 PTrade 盘后 JSON")
        self.manual_import_button.clicked.connect(self._handle_manual_import)
        self.reimport_button = QPushButton("重导")
        self.reimport_button.setObjectName("reimport_button")
        self.reimport_button.setToolTip("用原盘后 JSON 覆盖当前日期草稿")
        self.reimport_button.clicked.connect(self._handle_reimport)
        self.total_label = QLabel("账户总额 --")
        self.total_label.setObjectName("account_total_label")
        self.stock_value_label = QLabel("持仓市值 --")
        self.stock_value_label.setObjectName("account_stock_value_label")
        self.cash_label = QLabel("可用余额 --")
        self.cash_label.setObjectName("account_cash_label")
        self.opening_amount_label = QLabel("开仓金额 --")
        self.opening_amount_label.setObjectName("account_opening_amount_label")
        self.opening_amount_label.hide()
        for account_label in (self.total_label, self.stock_value_label, self.cash_label, self.opening_amount_label):
            account_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.draft_summary_label = QLabel("股票 -- | 待确认 --")
        self.draft_summary_label.setObjectName("draft_summary_label")
        self.stock_update_button = QPushButton("股票数据")
        self.stock_update_button.setObjectName("stock_update_button")
        self.stock_update_button.setToolTip("生成或更新股票基础数据，并维护交易日历")
        self.stock_update_button.clicked.connect(self._handle_stock_update)
        self.stock_search_input = StockSearchLineEdit()
        self.stock_search_input.setObjectName("stock_search_input")
        self.stock_search_input.setPlaceholderText("代码 / 名称 / 拼音")
        self.stock_search_input.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.stock_search_input.returnPressed.connect(self._handle_add_stock)
        self.stock_candidate_popup = QListWidget(self)
        self.stock_candidate_popup.setObjectName("stock_candidate_popup")
        self.stock_candidate_popup.setFocusPolicy(Qt.NoFocus)
        self.stock_candidate_popup.setMouseTracking(True)
        self.stock_candidate_popup.hide()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.stock_candidate_popup.itemEntered.connect(self._highlight_stock_candidate_item)
        self.stock_candidate_popup.itemClicked.connect(lambda item: self._handle_stock_candidate_activated(item.text()))
        self.stock_search_input.candidateNavigateRequested.connect(self._navigate_stock_candidate)
        self.stock_search_input.candidateConfirmRequested.connect(self._confirm_highlighted_stock_candidate)
        self.stock_search_input.textChanged.connect(self._refresh_stock_candidates)
        self.add_stock_button = QPushButton("添加")
        self.add_stock_button.setObjectName("add_stock_button")
        self.add_stock_button.setToolTip("添加开仓股票")
        self.add_stock_button.setEnabled(False)
        self.add_stock_button.clicked.connect(self._handle_add_stock)
        self.open_export_dir_button = QPushButton("目录")
        self.open_export_dir_button.setObjectName("open_export_dir_button")
        self.open_export_dir_button.setToolTip("打开订单 JSON 导出目录")
        self.open_export_dir_button.clicked.connect(self._handle_open_export_dir)
        self.open_export_dir_button.hide()
        self.check_export_button = QPushButton("检查")
        self.check_export_button.setObjectName("check_export_button")
        self.check_export_button.setToolTip("检查未确认订单、阻断项和提醒项")
        self.check_export_button.clicked.connect(self._handle_check_export)
        self.export_button = QPushButton("导出")
        self.export_button.setObjectName("export_button")
        self.export_button.setToolTip("导出订单 JSON")
        self.export_button.clicked.connect(self._handle_export)
        self.undo_delete_button = QPushButton("撤销")
        self.undo_delete_button.setObjectName("undo_delete_button")
        self.undo_delete_button.setToolTip("撤销最近一次删除")
        self.undo_delete_button.setEnabled(False)
        self.undo_delete_button.clicked.connect(self._handle_undo_delete)
        self.locate_unconfirmed_button = QPushButton("定位")
        self.locate_unconfirmed_button.setObjectName("locate_unconfirmed_button")
        self.locate_unconfirmed_button.setToolTip("定位第一条未确认或阻断项订单")
        self.locate_unconfirmed_button.setEnabled(False)
        self.locate_unconfirmed_button.clicked.connect(self._handle_locate_unconfirmed)
        self.status_label = StatusLabel("")
        self.status_label.setObjectName("startup_status_label")
        self.more_button = QPushButton("更多")
        self.more_button.setObjectName("more_actions_button")
        self.more_menu = QMenu(self.more_button)
        self.settings_action = self._make_more_action("设置目录及Token", self._handle_settings)
        self.manual_import_action = self._make_more_action("导入盘后JSON", self._handle_manual_import)
        self.stock_update_action = self._make_more_action("更新股票数据", self._handle_stock_update)
        self.open_export_dir_action = self._make_more_action("打开导出目录", self._handle_open_export_dir)
        self.delete_history_action = self._make_more_action("删除历史数据", self._handle_delete_history)
        self.open_export_dir_action.setEnabled(False)
        self.more_button.setMenu(self.more_menu)

        top_layout.addWidget(self.status_label, 0, 0, 1, 4)
        top_layout.addWidget(self.draft_summary_label, 0, 4)

        account_grid = QWidget()
        account_grid_layout = QGridLayout(account_grid)
        account_grid_layout.setContentsMargins(0, 0, 0, 0)
        account_grid_layout.setHorizontalSpacing(8)
        account_grid_layout.setVerticalSpacing(8)
        account_grid_layout.addWidget(self.total_label, 0, 0)
        account_grid_layout.addWidget(self.stock_value_label, 0, 1)
        account_grid_layout.addWidget(self.cash_label, 1, 0)
        account_grid_layout.addWidget(self.opening_amount_label, 1, 1)
        account_grid_layout.setColumnStretch(0, 1)
        account_grid_layout.setColumnStretch(1, 1)
        top_layout.addWidget(account_grid, 1, 0, 1, 5)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        self.stock_search_input.setMinimumWidth(20)
        self.stock_search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_layout.addWidget(self.stock_search_input, 1)
        action_layout.addWidget(self.add_stock_button)
        action_layout.addWidget(self._make_action_separator())
        action_layout.addWidget(self.undo_delete_button)
        action_layout.addWidget(self.locate_unconfirmed_button)
        action_layout.addWidget(self._make_action_separator())
        action_layout.addWidget(self.check_export_button)
        action_layout.addWidget(self.export_button)
        action_layout.addWidget(self._make_action_separator())
        action_layout.addWidget(self.more_button)
        top_layout.addWidget(action_row, 2, 0, 1, 5)
        layout.addWidget(self.account_bar)
        self.action_bar = self.account_bar

        self.tabs = StockFilterTabs()
        self.stock_scroll, self.stock_content, self.stock_layout = self._make_scroll_tab()
        self.tabs.addTab(QWidget(), "全部")
        self.tabs.addTab(QWidget(), "开仓")
        self.tabs.addTab(QWidget(), "持仓")
        self.tabs.currentChanged.connect(lambda index: self._apply_stock_filter())
        self.stock_jump_combo = AutoWidthComboBox()
        self.stock_jump_combo.setObjectName("stock_jump_combo")
        self.stock_jump_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.stock_jump_combo.activated[int].connect(self._handle_stock_jump_activated)
        self.stock_nav_bar = QWidget()
        self.stock_nav_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stock_nav_layout = QGridLayout(self.stock_nav_bar)
        self.stock_nav_layout.setContentsMargins(0, 5, 0, 5)
        self.stock_nav_layout.setHorizontalSpacing(8)
        self.stock_nav_layout.setVerticalSpacing(0)
        self.stock_nav_layout.setColumnStretch(0, 1)
        self.stock_nav_layout.setColumnStretch(1, 1)
        self.stock_nav_layout.setColumnStretch(2, 1)
        self.stock_nav_layout.addWidget(self.date_combo, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.stock_nav_layout.addWidget(self.tabs, 0, 1, Qt.AlignCenter)
        self.stock_nav_layout.addWidget(self.stock_jump_combo, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.stock_nav_bar, 0)
        layout.addWidget(self.stock_scroll, 1)

        if draft:
            self.set_draft(draft, default_to_holding=True)
        else:
            self._render_empty_state()
        self.refresh_stock_update_button()
        self.refresh_date_combo()
        self._set_top_button_cursors()
        if auto_update_stock_basic:
            QTimer.singleShot(0, self.start_stock_basic_update_if_needed)

    def _make_more_action(self, text: str, handler) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(handler)
        self.more_menu.addAction(action)
        return action

    def _resize_to_default_screen_half(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(self.minimumWidth(), 720)
            return
        available = screen.availableGeometry()
        width = self.minimumWidth()
        height = available.height()
        self.resize(width, height)
        self.move(available.right() - width + 1, available.y())

    def _make_action_separator(self) -> QLabel:
        separator = QLabel("|")
        separator.setObjectName("action_separator")
        separator.setAlignment(Qt.AlignCenter)
        return separator

    def _refresh_dynamic_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_pointing_cursors(self, *buttons: QPushButton) -> None:
        for button in buttons:
            button.setCursor(Qt.PointingHandCursor)

    def _set_top_button_cursors(self) -> None:
        self._set_pointing_cursors(
            self.settings_button,
            self.manual_import_button,
            self.reimport_button,
            self.stock_update_button,
            self.add_stock_button,
            self.open_export_dir_button,
            self.check_export_button,
            self.export_button,
            self.undo_delete_button,
            self.locate_unconfirmed_button,
            self.more_button,
        )

    def eventFilter(self, watched, event):  # noqa: N802
        if (
            event.type() == QEvent.MouseButtonPress
            and hasattr(self, "stock_candidate_popup")
            and self.stock_candidate_popup.isVisible()
        ):
            target = QApplication.widgetAt(event.globalPosition().toPoint())
            if target is None:
                self._hide_stock_candidate_popup()
            elif target not in {self.stock_candidate_popup, self.stock_search_input} and not self.stock_candidate_popup.isAncestorOf(target):
                self._hide_stock_candidate_popup()
        return super().eventFilter(watched, event)

    def set_startup_message(self, message: str) -> None:
        self.status_label.setText(message)

    def refresh_stock_update_button(self) -> None:
        if not self.service:
            self.set_stock_update_state("generate")
            return
        today = datetime.now().strftime("%Y%m%d")
        self.set_stock_update_state(self.service.stock_update_button_state(today))

    def set_stock_update_state(self, state: str) -> None:
        if state == "updating":
            self.stock_update_button.setText("更新中...")
            self.stock_update_button.setEnabled(False)
            self.stock_update_action.setText("股票数据更新中...")
            self.stock_update_action.setEnabled(False)
        elif state == "generate":
            self.stock_update_button.setText("生成数据")
            self.stock_update_button.setEnabled(True)
            self.stock_update_action.setText("生成股票数据")
            self.stock_update_action.setEnabled(True)
        elif state == "updated_disabled":
            self.stock_update_button.setText("数据已更新")
            self.stock_update_button.setEnabled(False)
            self.stock_update_action.setText("股票数据已更新")
            self.stock_update_action.setEnabled(False)
        elif state == "update_disabled_non_trade_day":
            self.stock_update_button.setText("更新数据")
            self.stock_update_button.setEnabled(False)
            self.stock_update_action.setText("更新股票数据")
            self.stock_update_action.setEnabled(False)
        else:
            self.stock_update_button.setText("更新数据")
            self.stock_update_button.setEnabled(True)
            self.stock_update_action.setText("更新股票数据")
            self.stock_update_action.setEnabled(True)

    def refresh_trade_calendar(self, *, silent: bool = False) -> None:
        if not self.service or not hasattr(self.service, "maintain_trade_calendar"):
            return
        today = datetime.now().strftime("%Y%m%d")
        try:
            count = self.service.maintain_trade_calendar(
                today=today,
                executable_dir=get_executable_dir(),
                user_data_dir=get_user_data_dir(),
            )
        except MissingTushareToken:
            return
        except Exception as exc:
            if not silent:
                self.status_label.setText(f"交易日历维护失败: {exc}")
            return
        if count and not silent:
            self.status_label.setText(f"交易日历已维护: {count} 条")

    def start_stock_basic_update_if_needed(self) -> None:
        self._start_stock_basic_update(only_if_needed=True)

    def _start_stock_basic_update(self, *, only_if_needed: bool) -> None:
        if not self.service:
            return
        stock_matcher = getattr(self.service, "stock_matcher", None)
        if stock_matcher is not None and not hasattr(stock_matcher, "sync_from_tushare"):
            return
        today = datetime.now().strftime("%Y%m%d")
        if only_if_needed and self.service.stock_update_button_state(today) not in {"generate", "update_enabled"}:
            return
        if self._stock_update_worker and self._stock_update_worker.isRunning():
            self.status_label.setText("股票基础数据正在更新...")
            return
        self.set_stock_update_state("updating")
        self.status_label.setText("正在更新股票基础数据...")
        try:
            plan = self.service.stock_update_fetch_plan(
                today=today,
                executable_dir=get_executable_dir(),
                user_data_dir=get_user_data_dir(),
            )
        except MissingTushareToken as exc:
            self.status_label.setText(str(exc))
            self.refresh_stock_update_button()
            return
        except Exception as exc:
            self.status_label.setText(f"股票基础数据更新失败: {exc}")
            self.refresh_stock_update_button()
            return
        self._stock_update_worker = StockUpdateWorker(
            plan["token"],
            plan["today"],
            plan["calendar_start_date"],
            plan["calendar_end_date"],
        )
        self._track_background_worker(self._stock_update_worker)
        self._stock_update_worker.finishedWithRows.connect(self._handle_stock_update_rows_loaded)
        self._stock_update_worker.failedWithMessage.connect(self._handle_stock_update_failed)
        self._stock_update_worker.finished.connect(self.refresh_stock_update_button)
        self._stock_update_worker.finished.connect(self._handle_stock_update_worker_finished)
        self._stock_update_worker.start()

    def refresh_date_combo(self) -> None:
        self.date_combo.blockSignals(True)
        self.date_combo.clear()
        dates = self.service.list_manage_dates() if self.service else []
        if not dates and self.draft:
            dates = [self.draft.manage_date]
        for manage_date in dates:
            self.date_combo.addItem(self._format_manage_date_label(manage_date), manage_date)
        if self.draft:
            index = self._date_combo_index(self.draft.manage_date)
            if index >= 0:
                self.date_combo.setCurrentIndex(index)
                self.date_combo.setItemText(index, self._date_combo_text(self.draft))
        self.date_combo.blockSignals(False)

    def set_draft(self, draft: SessionDraft, *, default_to_holding: bool = False) -> None:
        if self._daily_quotes_date != draft.manage_date:
            self._daily_quotes = {}
            self._daily_quotes_date = draft.manage_date
        self.draft = draft
        self.total_label.setText(f"账户总额 {self._format_money(draft.fund.portfolio_value)}")
        self.stock_value_label.setText(f"持仓市值 {self._format_money(draft.fund.stock_positions_value)}")
        opening_amount = self._opening_order_amount(draft)
        self.opening_amount_label.setText(f"开仓金额 {self._format_money(opening_amount)}")
        self.opening_amount_label.show()
        self.cash_label.setText(f"可用余额 {self._format_money(draft.fund.calibrated_cash)}")
        self._refresh_draft_summary()
        self.refresh_date_combo()

        self._render_stock_cards_or_empty(draft)

        self._refresh_tab_titles()
        if default_to_holding:
            self.tabs.setCurrentIndex(2)
        self._apply_stock_filter()
        self._apply_read_only_state()
        self.open_export_dir_action.setEnabled(bool(draft.export_json_path))
        self._refresh_locate_unconfirmed_button()
        self._refresh_check_export_button()
        self._schedule_daily_quotes_update(draft)

    def _render_empty_state(self) -> None:
        self._stock_cards_by_code = {}
        self.opening_amount_label.setText("开仓金额 0.00")
        self.opening_amount_label.show()
        self.draft_summary_label.setText("股票 -- | 待确认 --")
        self.tabs.setTabText(0, "全部")
        self.tabs.setTabText(1, "开仓")
        self.tabs.setTabText(2, "持仓")
        self._refresh_stock_jump_combo()
        self._clear_layout(self.stock_layout)
        self.stock_layout.addWidget(self._make_empty_state_label(read_only=False))
        self.stock_layout.addStretch(1)

    def _render_stock_cards_or_empty(self, draft: SessionDraft) -> None:
        self._remember_order_input_widths()
        self._stock_cards_by_code = {}
        self._clear_layout(self.stock_layout)
        if draft.stocks:
            for stock in draft.stocks:
                card = self._make_stock_card(stock)
                self._stock_cards_by_code[stock.ts_code] = card
                self.stock_layout.addWidget(card)
        else:
            self.stock_layout.addWidget(self._make_empty_state_label(read_only=draft.read_only))
        self.stock_layout.addStretch(1)
        self._prune_order_input_widths(draft)

    def _make_empty_state_label(self, *, read_only: bool) -> QLabel:
        text = "历史日期无本地数据。" if read_only else "未导入盘后 JSON，也可以直接添加股票并编辑开仓交易单。"
        empty_label = QLabel(text)
        empty_label.setObjectName("empty_state_label")
        return empty_label

    def _refresh_draft_summary(self) -> None:
        if not self.draft:
            self.draft_summary_label.setText("股票 -- | 待确认 --")
            return
        total = len(self.draft.stocks)
        unconfirmed = sum(1 for stock in self.draft.stocks for order in stock.orders if not order.confirmed)
        state_text = {
            "empty": "无数据",
            "draft": "草稿",
            "exported": "已导出",
            "modified_after_export": "导出后修改",
        }.get(self.draft.export_state, self.draft.export_state)
        self.draft_summary_label.setText(f"股票 {total} | 待确认 {unconfirmed} | {state_text}")
        self._refresh_locate_unconfirmed_button()

    def _refresh_locate_unconfirmed_button(self) -> None:
        if not hasattr(self, "locate_unconfirmed_button"):
            return
        self.locate_unconfirmed_button.setEnabled(self._first_attention_stock() is not None)

    def _refresh_check_export_button(self) -> None:
        if not hasattr(self, "check_export_button"):
            return
        tone = "clean"
        tooltip = "检查未确认订单、阻断项和提醒项"
        can_export = False
        if self.draft:
            validation = validate_export(self.draft)
            pending = self._pending_order_lines(self.draft)
            can_export = bool(self.service and self.draft.export_json_path and not validation.blockers)
            if validation.blockers:
                tone = "blocker"
                tooltip = f"阻断项 {len(validation.blockers)} 个"
            elif pending:
                tone = "pending"
                tooltip = f"待确认项 {len(pending)} 个"
            elif validation.warnings:
                tone = "warning"
                tooltip = f"提醒项 {len(validation.warnings)} 个"
        self.check_export_button.setProperty("tone", tone)
        self.check_export_button.setToolTip(tooltip)
        self._refresh_dynamic_style(self.check_export_button)
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(can_export)

    def _date_combo_text(self, draft: SessionDraft) -> str:
        suffix = " 只读" if draft.read_only else ""
        return f"{self._format_manage_date_label(draft.manage_date)}{suffix}"

    def _format_manage_date_label(self, manage_date: str) -> str:
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        try:
            weekday = weekdays[datetime.strptime(manage_date, "%Y%m%d").weekday()]
        except ValueError:
            return manage_date
        return f"{manage_date} {weekday}"

    def _date_combo_index(self, manage_date: str) -> int:
        for index in range(self.date_combo.count()):
            if self.date_combo.itemData(index, Qt.UserRole) == manage_date:
                return index
        return -1

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
        for card in self._stock_cards_by_code.values():
            if filter_index == 1:
                card.setVisible(not card.stock.is_holding)
            elif filter_index == 2:
                card.setVisible(card.stock.is_holding)
            else:
                card.setVisible(True)
        self._refresh_stock_jump_combo()

    def _refresh_stock_jump_combo(self) -> None:
        if not hasattr(self, "stock_jump_combo"):
            return
        self.stock_jump_combo.blockSignals(True)
        self.stock_jump_combo.clear()
        for card in self._visible_stock_cards_in_order():
            self.stock_jump_combo.addItem(f"{card.stock.ts_code} {card.stock.stock_name}", card.stock.ts_code)
        self.stock_jump_combo.setEnabled(self.stock_jump_combo.count() > 0)
        self.stock_jump_combo.blockSignals(False)

    def _visible_stock_cards_in_order(self) -> list[StockCard]:
        if not self.draft:
            return []
        cards = []
        for stock in self.draft.stocks:
            card = self._stock_cards_by_code.get(stock.ts_code)
            if card is not None and not card.isHidden():
                cards.append(card)
        return cards

    def _handle_stock_jump_activated(self, index: int) -> None:
        ts_code = self.stock_jump_combo.itemData(index, Qt.UserRole)
        if not ts_code:
            return
        card = self._stock_cards_by_code.get(str(ts_code))
        if card:
            self.stock_scroll.ensureWidgetVisible(card)
            self.status_label.setText(f"已定位: {card.stock.ts_code} {card.stock.stock_name}")

    def _make_scroll_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(0)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        content = QWidget()
        content.setMinimumHeight(0)
        tab_layout = QVBoxLayout(content)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(8)
        scroll.setWidget(content)
        return scroll, content, tab_layout

    def _make_stock_card(self, stock):
        card = StockCard(
            stock,
            read_only=bool(self.draft and self.draft.read_only),
            daily_quote=self._daily_quotes.get(stock.ts_code),
        )
        card.confirmRequested.connect(self._handle_order_confirm)
        card.deleteRequested.connect(self._handle_order_delete)
        card.orderChanged.connect(self._handle_order_change)
        card.orderTypeChanged.connect(self._handle_order_type_change)
        card.addOrderRequested.connect(self._handle_add_order)
        card.deleteStockRequested.connect(self._handle_stock_delete)
        self._restore_order_input_widths(card)
        return card

    def _remember_order_input_widths(self) -> None:
        for row in self.stock_content.findChildren(OrderRow):
            if row.order.id is None:
                continue
            self._order_input_widths_by_id[row.order.id] = (
                row.price_input.integer_width(),
                row.shares_input.integer_width(),
            )

    def _restore_order_input_widths(self, card: StockCard) -> None:
        for row in card.findChildren(OrderRow):
            if row.order.id is None:
                continue
            widths = self._order_input_widths_by_id.get(row.order.id)
            if widths is None:
                continue
            price_width, shares_width = widths
            row.price_input.set_integer_width(price_width)
            row.shares_input.set_integer_width(shares_width)

    def _prune_order_input_widths(self, draft: SessionDraft) -> None:
        current_order_ids = {order.id for stock in draft.stocks for order in stock.orders if order.id is not None}
        self._order_input_widths_by_id = {
            order_id: widths
            for order_id, widths in self._order_input_widths_by_id.items()
            if order_id in current_order_ids
        }

    def _schedule_daily_quotes_update(self, draft: SessionDraft) -> None:
        manage_date = draft.manage_date
        QTimer.singleShot(0, lambda: self._start_daily_quotes_update(manage_date))

    def _start_daily_quotes_update(self, manage_date: str) -> None:
        if not self.draft or self.draft.manage_date != manage_date:
            return
        draft = self.draft
        if not self.service or not draft.stocks or not hasattr(self.service, "cached_daily_quotes"):
            return
        ts_codes = [stock.ts_code for stock in draft.stocks]
        if self._daily_quotes_date == draft.manage_date and all(ts_code in self._daily_quotes for ts_code in ts_codes):
            return
        try:
            cached_quotes = self.service.cached_daily_quotes(draft.manage_date, ts_codes=ts_codes)
        except Exception:
            cached_quotes = {}
        if cached_quotes:
            self._handle_daily_quotes_loaded(draft.manage_date, cached_quotes)
        if hasattr(self.service, "has_daily_quote_cache") and self.service.has_daily_quote_cache(draft.manage_date):
            return
        if not self._auto_update_daily_quotes:
            return
        worker = self._daily_quote_workers_by_date.get(draft.manage_date)
        if worker and worker.isRunning():
            return
        try:
            token = load_tushare_token(get_executable_dir(), get_user_data_dir())
        except Exception:
            return
        if self._daily_quotes_worker and self._daily_quotes_worker.isRunning():
            self._daily_quotes_worker.requestInterruption()
        self._daily_quotes_worker = DailyQuotesWorker(
            draft.manage_date,
            token,
            ts_codes,
        )
        self._daily_quote_workers_by_date[draft.manage_date] = self._daily_quotes_worker
        self._track_background_worker(self._daily_quotes_worker)
        self._daily_quotes_worker.finishedWithRows.connect(self._handle_daily_quote_rows_loaded)
        self._daily_quotes_worker.finished.connect(self._handle_daily_quotes_worker_finished)
        self._daily_quotes_worker.start()

    def _handle_daily_quote_rows_loaded(self, manage_date: str, rows: list[dict[str, object]]) -> None:
        if not rows or not self.service:
            return
        try:
            quotes = self.service.cache_daily_quote_rows(
                manage_date,
                rows,
                ts_codes=[stock.ts_code for stock in self.draft.stocks] if self.draft and self.draft.manage_date == manage_date else None,
            )
        except Exception:
            return
        if not self.draft or self.draft.manage_date != manage_date:
            return
        self._handle_daily_quotes_loaded(manage_date, quotes)

    def _handle_daily_quotes_loaded(self, manage_date: str, quotes: dict[str, DailyQuote]) -> None:
        if not self.draft or self.draft.manage_date != manage_date or not quotes:
            return
        if self._daily_quotes_date != manage_date:
            self._daily_quotes = {}
        self._daily_quotes.update(quotes)
        self._daily_quotes_date = manage_date
        for ts_code, quote in quotes.items():
            card = self._stock_cards_by_code.get(ts_code)
            if card:
                card.set_daily_quote(quote)

    def _handle_daily_quotes_worker_finished(self) -> None:
        worker = self.sender()
        if worker is self._daily_quotes_worker:
            self._daily_quotes_worker = None
        if worker:
            self._background_workers.discard(worker)
            stale_dates = [
                manage_date
                for manage_date, date_worker in self._daily_quote_workers_by_date.items()
                if date_worker is worker
            ]
            for manage_date in stale_dates:
                self._daily_quote_workers_by_date.pop(manage_date, None)
        if worker:
            worker.deleteLater()

    def closeEvent(self, event):  # noqa: N802
        self._stop_background_workers()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def _track_background_worker(self, worker: QThread) -> None:
        self._background_workers.add(worker)

    def _stop_background_workers(self) -> None:
        for worker in list(self._background_workers):
            if worker and worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                worker.wait(6500)
            if worker is None or not worker.isRunning():
                self._background_workers.discard(worker)
        self._daily_quotes_worker = None
        self._stock_update_worker = None
        self._daily_quote_workers_by_date.clear()

    def _apply_read_only_state(self) -> None:
        read_only = bool(self.draft and self.draft.read_only)
        self.stock_search_input.setEnabled(not read_only)
        self._refresh_add_stock_enabled()
        self.reimport_button.setEnabled(not read_only and bool(self.draft and self.draft.ptrade_json_path))

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                for digit_input in widget.findChildren(DigitInput):
                    digit_input.clear_cursor()
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
        self._refresh_check_export_button()
        opening_amount = self._opening_order_amount(self.draft)
        self.opening_amount_label.setText(f"开仓金额 {self._format_money(opening_amount)}")
        self.opening_amount_label.show()
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
        self.undo_delete_button.setEnabled(True)

    def _handle_stock_delete(self, stock) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not self.draft:
            self.status_label.setText("订单服务未就绪")
            return
        reply = QMessageBox.question(
            self,
            "删除股票单元",
            f"删除 {stock.ts_code} {stock.stock_name} 及其全部订单？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.status_label.setText("已取消删除股票")
            return
        self.draft, self._last_deleted_snapshot = self.service.delete_stock_with_snapshot(self.draft.manage_date, stock.ts_code)
        self.undo_delete_button.setEnabled(True)
        self.status_label.setText("股票已删除")
        self.set_draft(self.draft)

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
        if self.draft.export_state == "empty":
            self.draft = self.service.open_blank_manage_date(self.draft.manage_date)
        query = self.stock_search_input.text().strip()
        if not query:
            self.status_label.setText("请输入股票代码或名称")
            return
        stock = self._exact_stock_from_input(query)
        if not stock:
            self.status_label.setText("请先选择唯一匹配的股票")
            self._refresh_add_stock_enabled()
            return
        try:
            self.draft = self.service.add_manual_stock_by_code(
                self.draft.manage_date,
                stock["ts_code"],
                stock_name=stock["name"],
            )
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText("已添加股票")
        self._selected_stock_candidate = None
        self.stock_search_input.clear()
        self.set_draft(self.draft)
        self.tabs.setCurrentIndex(1)

    def _refresh_stock_candidates(self, query: str) -> None:
        self._hide_stock_candidate_popup()
        self._stock_candidate_by_label.clear()
        selected_label = self._stock_label(self._selected_stock_candidate) if self._selected_stock_candidate else ""
        if selected_label and self._normalize_stock_text(query) == self._normalize_stock_text(selected_label):
            self._stock_candidate_by_label[selected_label] = self._selected_stock_candidate
            self._set_stock_candidate_labels([selected_label])
            self._refresh_add_stock_enabled()
            return
        self._selected_stock_candidate = None
        if not self.service or not query.strip():
            self._set_stock_candidate_labels([])
            self.add_stock_button.setEnabled(False)
            return
        try:
            candidates = self.service.search_manual_stock_candidates(query.strip(), limit=8)
        except Exception:
            self._set_stock_candidate_labels([])
            self.add_stock_button.setEnabled(False)
            return
        labels = []
        for stock in candidates:
            label = self._stock_label(stock)
            self._stock_candidate_by_label[label] = stock
            labels.append(label)
        self._set_stock_candidate_labels(labels)
        self._refresh_add_stock_enabled()
        if labels and self.stock_search_input.hasFocus() and not self._suppress_candidate_popup:
            self._show_stock_candidate_popup(labels)

    def _set_stock_candidate_labels(self, labels: list[str]) -> None:
        self.stock_candidate_popup.clear()
        for label in labels:
            self.stock_candidate_popup.addItem(QListWidgetItem(label))
        self.stock_search_input.set_candidate_popup_visible(bool(labels))
        self.stock_search_input.set_candidate_has_highlight(False)

    def _show_stock_candidate_popup(self, labels: list[str]) -> None:
        width = max(
            self.stock_search_input.width(),
            max(self.stock_search_input.fontMetrics().horizontalAdvance(label) + 48 for label in labels),
        )
        row_height = max(30, self.stock_search_input.fontMetrics().height() + 12)
        self.stock_candidate_popup.setFixedWidth(width)
        self.stock_candidate_popup.setFixedHeight(min(len(labels), 8) * row_height + 2)
        self.stock_candidate_popup.setCurrentRow(-1)
        popup_pos = self.mapFromGlobal(self.stock_search_input.mapToGlobal(QPoint(0, self.stock_search_input.height())))
        self.stock_candidate_popup.move(popup_pos)
        self.stock_candidate_popup.raise_()
        self.stock_candidate_popup.show()
        self.stock_search_input.set_candidate_popup_visible(True)

    def _hide_stock_candidate_popup(self) -> None:
        if hasattr(self, "stock_candidate_popup"):
            self.stock_candidate_popup.hide()
        if hasattr(self, "stock_search_input"):
            self.stock_search_input.set_candidate_popup_visible(False)

    def _navigate_stock_candidate(self, step: int) -> None:
        row_count = self.stock_candidate_popup.count()
        if row_count <= 0:
            self._hide_stock_candidate_popup()
            return
        current_row = self.stock_candidate_popup.currentRow()
        if current_row < 0:
            next_row = 0 if step > 0 else row_count - 1
        else:
            next_row = max(0, min(row_count - 1, current_row + step))
        self.stock_candidate_popup.setCurrentRow(next_row)
        self.stock_search_input.set_candidate_has_highlight(True)

    def _highlight_stock_candidate_item(self, item: QListWidgetItem) -> None:
        self.stock_candidate_popup.setCurrentItem(item)
        self.stock_search_input.set_candidate_has_highlight(True)

    def _confirm_highlighted_stock_candidate(self) -> None:
        item = self.stock_candidate_popup.currentItem()
        if item is None and self.stock_candidate_popup.count() > 0:
            item = self.stock_candidate_popup.item(0)
        if item is not None:
            self._handle_stock_candidate_activated(item.text())

    def _handle_stock_candidate_activated(self, label: str) -> None:
        if self.draft and self.draft.read_only:
            self.status_label.setText("历史日期只读")
            return
        if not self.service or not self.draft:
            self.status_label.setText("订单服务未就绪")
            return
        stock = self._candidate_by_label(label)
        if not stock:
            return
        self._selected_stock_candidate = stock
        self._suppress_candidate_popup = True
        self.stock_search_input.setText(self._stock_label(stock))
        self._suppress_candidate_popup = False
        self._hide_stock_candidate_popup()
        self._refresh_add_stock_enabled()
        self.status_label.setText(f"已选择股票: {stock['ts_code']} {stock['name']}")

    def _stock_label(self, stock: dict[str, str] | None) -> str:
        if not stock:
            return ""
        return f"{stock['ts_code']} {stock['name']}"

    def _normalize_stock_text(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _candidate_by_label(self, label: str) -> dict[str, str] | None:
        normalized = self._normalize_stock_text(label)
        for candidate_label, stock in self._stock_candidate_by_label.items():
            if self._normalize_stock_text(candidate_label) == normalized:
                return stock
        return None

    def _refresh_add_stock_enabled(self) -> None:
        read_only = bool(self.draft and self.draft.read_only)
        self.add_stock_button.setEnabled(not read_only and self._exact_stock_from_input(self.stock_search_input.text()) is not None)

    def _exact_stock_from_input(self, query: str) -> dict[str, str] | None:
        if not self.service:
            return None
        text = self._normalize_stock_text(query)
        if not text:
            return None
        selected_label = self._stock_label(self._selected_stock_candidate) if self._selected_stock_candidate else ""
        if selected_label and self._normalize_stock_text(selected_label) == text:
            return self._selected_stock_candidate
        for label, stock in self._stock_candidate_by_label.items():
            if self._normalize_stock_text(label) == text:
                return stock
        parts = text.split()
        if len(parts) >= 2:
            code_text = parts[0]
            name_text = " ".join(parts[1:])
            try:
                code_candidates = self.service.search_manual_stock_candidates(code_text, limit=2)
            except Exception:
                code_candidates = []
            code_matches = [
                stock
                for stock in code_candidates
                if self._normalize_stock_text(str(stock["name"])) == name_text
                and code_text.upper() in {str(stock["ts_code"]).upper(), str(stock.get("symbol") or "").upper()}
            ]
            unique_code_matches = {stock["ts_code"]: stock for stock in code_matches}
            if len(unique_code_matches) == 1:
                return next(iter(unique_code_matches.values()))
        try:
            candidates = self.service.search_manual_stock_candidates(text, limit=20)
        except Exception:
            return None
        exact_matches = []
        text_upper = text.upper()
        for stock in candidates:
            ts_code = str(stock["ts_code"])
            symbol = str(stock.get("symbol") or ts_code.split(".", 1)[0])
            name = str(stock["name"])
            label = self._stock_label(stock)
            if text_upper in {ts_code.upper(), symbol.upper()} or text == name or text == label:
                exact_matches.append(stock)
        unique = {stock["ts_code"]: stock for stock in exact_matches}
        if len(unique) == 1:
            return next(iter(unique.values()))
        return None

    def _handle_date_changed(self, manage_date: str) -> None:
        current_data = self.date_combo.currentData(Qt.UserRole)
        manage_date = str(current_data or manage_date.split()[0])
        self._open_manage_date(manage_date)

    def _open_manage_date(self, manage_date: str) -> None:
        if not manage_date or not self.service:
            return
        if self.draft and self.draft.manage_date == manage_date:
            return
        try:
            self.draft = self.service.load_draft(manage_date)
        except KeyError:
            self.draft = self.service.empty_manage_date_view(manage_date)
        self.status_label.setText("历史日期只读，可重新导出" if self.draft.read_only else "已切换管理日期")
        self.set_draft(self.draft, default_to_holding=True)

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
        self.refresh_trade_calendar()
        self.refresh_date_combo()
        self.refresh_stock_update_button()
        self.status_label.setText("目录设置已保存")

    def _tushare_token_hint(self, user_data_dir: Path) -> str:
        try:
            token = load_tushare_token(get_executable_dir(), user_data_dir)
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
        self.refresh_trade_calendar(silent=True)
        self.status_label.setText("导入完成")
        self.set_draft(self.draft, default_to_holding=True)

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
        self._start_stock_basic_update(only_if_needed=False)

    def _handle_stock_update_finished(self, count: int) -> None:
        self.status_label.setText(f"股票基础数据已更新: {count} 条")
        self.refresh_date_combo()

    def _handle_stock_update_rows_loaded(self, calendar_rows: list[dict[str, object]], stock_rows: list[dict[str, object]]) -> None:
        if not self.service:
            return
        try:
            count = self.service.apply_stock_basic_update(
                today=datetime.now().strftime("%Y%m%d"),
                calendar_rows=calendar_rows,
                stock_rows=stock_rows,
            )
        except Exception as exc:
            self.status_label.setText(f"股票基础数据更新失败: {exc}")
            return
        self._handle_stock_update_finished(count)

    def _handle_stock_update_worker_finished(self) -> None:
        worker = self.sender()
        if worker is self._stock_update_worker:
            self._stock_update_worker = None
        if worker:
            self._background_workers.discard(worker)
        if worker:
            worker.deleteLater()

    def _handle_stock_update_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def _handle_undo_delete(self) -> None:
        if not self.service or not self._last_deleted_snapshot:
            return
        self.draft = self.service.restore_deleted_order(self._last_deleted_snapshot)
        self._last_deleted_snapshot = None
        self.undo_delete_button.setEnabled(False)
        self.status_label.setText("已撤销删除")
        self.set_draft(self.draft)

    def _handle_locate_unconfirmed(self) -> None:
        if not self.draft:
            return
        stock = self._first_attention_stock()
        if not stock:
            self.status_label.setText("没有未确认或阻断项订单")
            self._refresh_locate_unconfirmed_button()
            return
        self.tabs.setCurrentIndex(0)
        card = self._stock_cards_by_code.get(stock.ts_code)
        if card:
            self.stock_scroll.ensureWidgetVisible(card)
        self.status_label.setText(f"已定位需处理: {stock.ts_code} {stock.stock_name}")

    def _first_attention_stock(self):
        if not self.draft:
            return None
        validation = validate_export(self.draft)
        for stock in self.draft.stocks:
            if any(not order.confirmed for order in stock.orders):
                return stock
            prefix = f"{stock.ts_code} {stock.stock_name}"
            if any(blocker.startswith(prefix) for blocker in validation.blockers):
                return stock
        return None

    def _handle_open_export_dir(self) -> None:
        if not self.draft or not self.draft.export_json_path:
            self.status_label.setText("导出路径未配置")
            return
        directory = Path(self.draft.export_json_path).parent
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        self.status_label.setText(f"已打开导出目录: {directory}")

    def _handle_delete_history(self) -> None:
        if not self.service:
            self.status_label.setText("数据服务未就绪")
            return
        stored_dates = self.service.drafts.list_manage_dates()
        if not stored_dates:
            self.status_label.setText("没有可删除的历史数据")
            return
        manage_date = self._select_history_date_for_delete(stored_dates)
        if not manage_date:
            self.status_label.setText("已取消删除历史数据")
            return
        reply = QMessageBox.question(
            self,
            "确认删除历史数据",
            f"删除 {self._format_manage_date_label(manage_date)} 的全部数据？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.status_label.setText("已取消删除历史数据")
            return
        self.service.delete_manage_date(manage_date)
        if self.draft and self.draft.manage_date == manage_date:
            self.draft = self.service.empty_manage_date_view(manage_date)
            self.set_draft(self.draft, default_to_holding=True)
        else:
            self.refresh_date_combo()
        self.status_label.setText(f"已删除历史数据: {manage_date}")

    def _select_history_date_for_delete(self, manage_dates: list[str]) -> str | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("删除历史数据")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        label = QLabel("选择要删除的管理日期")
        combo = AutoWidthComboBox(dialog)
        combo.setObjectName("delete_history_date_combo")
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for manage_date in manage_dates:
            combo.addItem(self._format_manage_date_label(manage_date), manage_date)
        layout.addWidget(label)
        layout.addWidget(combo)
        buttons = QHBoxLayout()
        cancel_button = QPushButton("取消")
        delete_button = QPushButton("删除")
        delete_button.setObjectName("delete_history_confirm_button")
        self._set_pointing_cursors(cancel_button, delete_button)
        cancel_button.clicked.connect(dialog.reject)
        delete_button.clicked.connect(dialog.accept)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(delete_button)
        layout.addLayout(buttons)
        dialog.setMinimumWidth(max(280, combo.sizeHint().width() + 80))
        if dialog.exec() != QDialog.Accepted:
            return None
        return str(combo.currentData(Qt.UserRole) or "")

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
        layout.addWidget(self._make_export_check_section("阻断项", blockers, "blocker"))
        layout.addWidget(self._make_export_check_section("待确认", pending, "pending"))
        layout.addWidget(self._make_export_check_section("提醒项", warnings, "warning"))
        buttons = QHBoxLayout()
        locate_button = QPushButton("定位")
        close_button = QPushButton("关闭")
        self._set_pointing_cursors(locate_button, close_button)
        locate_button.setEnabled(self._first_attention_stock() is not None)
        locate_button.clicked.connect(lambda: (dialog.accept(), self._handle_locate_unconfirmed()))
        close_button.clicked.connect(dialog.accept)
        buttons.addStretch(1)
        buttons.addWidget(locate_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        all_lines = [summary_text, *pending, *blockers, *warnings]
        content_width = max((dialog.fontMetrics().horizontalAdvance(line) for line in all_lines), default=280)
        dialog.setMinimumWidth(max(360, min(content_width + 96, 920)))
        dialog.adjustSize()
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
