from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QWidget

from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.config import load_config
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from ptrade_order_tool.ui import main_window as main_window_module
from ptrade_order_tool.ui.main_window import AutoWidthComboBox, MainWindow
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.settings_dialog import SettingsDialog
from ptrade_order_tool.ui.stock_card import StockCard
from tests.test_app_service_actions import make_service
from tests.test_ptrade_importer import FIXTURE, FakeStockMatcher


def test_settings_dialog_round_trip(qtbot):
    dialog = SettingsDialog(AppConfig(ptrade_data_dir="/a", order_data_dir="/b"), token_hint="当前: abcd...wxyz")
    qtbot.addWidget(dialog)
    dialog.ptrade_data_dir_input.setText("/new/ptrade")
    dialog.order_data_dir_input.setText("/new/order")
    dialog.tushare_token_input.setText("new-token")

    config = dialog.to_config(AppConfig(last_opened_manage_date="20260225"))

    assert config.ptrade_data_dir == "/new/ptrade"
    assert config.order_data_dir == "/new/order"
    assert config.last_opened_manage_date == "20260225"
    assert dialog.tushare_token_input.placeholderText() == "当前: abcd...wxyz"
    assert dialog.token_text() == "new-token"


def test_settings_dialog_browse_buttons_fill_directories(qtbot, monkeypatch, tmp_path):
    dialog = SettingsDialog(AppConfig())
    qtbot.addWidget(dialog)
    selected = tmp_path / "ptrade_data"
    selected.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(selected))

    qtbot.mouseClick(dialog.findChild(QPushButton, "ptrade_data_dir_input_browse"), Qt.LeftButton)

    assert dialog.ptrade_data_dir_input.text() == str(selected)


def test_service_lists_manage_dates(sqlite_conn, tmp_path):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )

    assert service.list_manage_dates() == ["20260226", "20260225", "20260224"]


def test_date_combo_switches_to_historical_read_only(qtbot, sqlite_conn, tmp_path):
    service, _, _ = make_service(sqlite_conn, tmp_path, now_provider=lambda: datetime(2026, 2, 26, 17, 31))
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    window = MainWindow(service.load_draft("20260226"), service)
    qtbot.addWidget(window)

    for index in range(window.date_combo.count()):
        if window.date_combo.itemData(index, Qt.UserRole) == "20260225":
            window.date_combo.setCurrentIndex(index)
            break

    assert window.draft.manage_date == "20260225"
    assert window.draft.read_only is True
    assert window.tabs.currentIndex() == 2
    assert "历史日期只读" in window.status_label.text()


def test_date_combo_activation_switches_date(qtbot, sqlite_conn, tmp_path):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    window = MainWindow(service.load_draft("20260226"), service)
    qtbot.addWidget(window)
    target_index = next(
        index
        for index in range(window.date_combo.count())
        if window.date_combo.itemData(index, Qt.UserRole) == "20260225"
    )

    window.date_combo.setCurrentIndex(target_index)

    assert window.draft.manage_date == "20260225"


def test_switching_dates_keeps_running_daily_quote_workers_alive(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    workers = []

    class FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class RunningDailyWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
            self.finished = FakeSignal()
            self.interrupted = False
            workers.append(self)

        def start(self):
            return None

        def isRunning(self):
            return True

        def requestInterruption(self):
            self.interrupted = True

        def quit(self):
            return None

        def wait(self, _ms):
            return True

    monkeypatch.setattr(main_window_module, "load_tushare_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(main_window_module, "DailyQuotesWorker", RunningDailyWorker)

    window = MainWindow(service.load_draft("20260226"), service, auto_update_stock_basic=False, auto_update_daily_quotes=True)
    qtbot.addWidget(window)
    window._start_daily_quotes_update("20260226")
    window._open_manage_date("20260225")
    window._start_daily_quotes_update("20260225")

    assert len(workers) == 2
    assert workers[0].interrupted is True
    assert workers[0] in window._background_workers
    assert workers[1] in window._background_workers
    assert window._daily_quotes_worker is workers[1]


def test_daily_quote_update_deduplicates_in_flight_trade_date(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    workers = []

    class FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class RunningDailyWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
            self.finished = FakeSignal()
            self.manage_date = args[0]
            workers.append(self)

        def start(self):
            return None

        def isRunning(self):
            return True

        def requestInterruption(self):
            return None

        def quit(self):
            return None

        def wait(self, _ms):
            return True

    monkeypatch.setattr(main_window_module, "load_tushare_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(main_window_module, "DailyQuotesWorker", RunningDailyWorker)

    window = MainWindow(service.load_draft("20260225"), service, auto_update_stock_basic=False, auto_update_daily_quotes=True)
    qtbot.addWidget(window)
    window._start_daily_quotes_update("20260225")
    window._start_daily_quotes_update("20260225")

    assert len(workers) == 1
    assert window._daily_quote_workers_by_date == {"20260225": workers[0]}


def test_stale_daily_quote_rows_are_cached_without_refreshing_current_ui(qtbot, sqlite_conn, tmp_path):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    window = MainWindow(service.load_draft("20260226"), service, auto_update_stock_basic=False, auto_update_daily_quotes=False)
    qtbot.addWidget(window)
    rows = [
        {
            "ts_code": "002153.SZ",
            "trade_date": "20260225",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "pre_close": 10,
            "change": 0.5,
            "pct_chg": 5,
            "vol": 10000,
            "amount": 200000,
        }
    ]

    window._handle_daily_quote_rows_loaded("20260225", rows)

    assert service.cached_daily_quotes("20260225", ts_codes=["002153.SZ"])["002153.SZ"].close == Decimal("10.5")
    assert window.draft.manage_date == "20260226"
    assert all(card.findChild(QWidget, "stock_daily_quote").isHidden() for card in window.findChildren(StockCard))


def test_rapid_date_switching_keeps_state_and_worker_lifecycle_stable(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, _, _ = make_service(sqlite_conn, tmp_path)
    for manage_date in ("20260226", "20260227", "20260228"):
        imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
        imported.manage_date = manage_date
        service.drafts.create_draft(
            imported,
            expected_trade_date=None,
            ptrade_json_path=f"/tmp/{manage_date}.json",
            export_json_path=f"/tmp/order_data/{manage_date}.json",
        )
    workers = []

    class FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class RunningDailyWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
            self.finished = FakeSignal()
            self.interrupted = False
            self.manage_date = args[0]
            workers.append(self)

        def start(self):
            return None

        def isRunning(self):
            return True

        def requestInterruption(self):
            self.interrupted = True

        def quit(self):
            return None

        def wait(self, _ms):
            return True

    monkeypatch.setattr(main_window_module, "load_tushare_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(main_window_module, "DailyQuotesWorker", RunningDailyWorker)

    window = MainWindow(service.load_draft("20260228"), service, auto_update_stock_basic=False, auto_update_daily_quotes=True)
    qtbot.addWidget(window)
    for manage_date in ("20260227", "20260226", "20260225", "20260228", "20260225"):
        window._open_manage_date(manage_date)
        window._start_daily_quotes_update(manage_date)

    assert window.draft.manage_date == "20260225"
    assert window.tabs.currentIndex() == 2
    assert all(worker in window._background_workers for worker in workers)
    assert all(worker.interrupted for worker in workers[:-1])
    assert window._daily_quotes_worker is workers[-1]


def test_historical_draft_disables_editing_controls(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    service._now_provider = lambda: datetime(2026, 2, 26, 17, 31)
    window = MainWindow(service.load_draft("20260225"), service, auto_update_stock_basic=False)
    qtbot.addWidget(window)

    rows = window.findChildren(OrderRow)
    add_buttons = [button for card in window.findChildren(StockCard) for button in card.findChildren(type(window.export_button)) if button.objectName().startswith("add_order_")]

    assert window.stock_search_input.isEnabled() is False
    assert window.add_stock_button.isEnabled() is False
    assert window.manual_import_button.isEnabled() is False
    assert window.manual_import_action.isEnabled() is False
    assert all(not row.confirm_button.isEnabled() for row in rows)
    assert all(not row.delete_button.isEnabled() for row in rows)
    assert all(button.text() == "+" for button in add_buttons)
    assert all(not button.isEnabled() for button in add_buttons)


def test_historical_draft_blocks_manual_import_handler(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    service._now_provider = lambda: datetime(2026, 2, 26, 17, 31)
    window = MainWindow(service.load_draft("20260225"), service, auto_update_stock_basic=False)
    qtbot.addWidget(window)
    called = {"dialog": False}
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: called.__setitem__("dialog", True) or ("", ""))

    window._handle_manual_import()

    assert called["dialog"] is False
    assert "历史日期只读" in window.status_label.text()


def test_delete_history_action_removes_selected_date(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, _, _ = make_service(sqlite_conn, tmp_path, now_provider=lambda: datetime(2026, 2, 26, 17, 31))
    imported = parse_ptrade_json(FIXTURE, FakeStockMatcher())
    imported.manage_date = "20260226"
    service.drafts.create_draft(
        imported,
        expected_trade_date=None,
        ptrade_json_path="/tmp/20260226.json",
        export_json_path="/tmp/order_data/20260226.json",
    )
    window = MainWindow(service.load_draft("20260226"), service, auto_update_stock_basic=False)
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_select_history_date_for_delete", lambda dates: "20260225")
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window.delete_history_action.trigger()

    assert service.drafts.list_manage_dates() == ["20260226"]
    assert "20260225" in [window.date_combo.itemData(index, Qt.UserRole) for index in range(window.date_combo.count())]
    assert "已删除历史数据: 20260225" in window.status_label.text()

    for index in range(window.date_combo.count()):
        if window.date_combo.itemData(index, Qt.UserRole) == "20260225":
            window.date_combo.setCurrentIndex(index)
            break

    assert window.draft.manage_date == "20260225"
    assert window.draft.export_state == "empty"
    assert window.draft.read_only is True
    assert window.tabs.tabText(0) == "全部 0"
    assert "无数据" in window.draft_summary_label.text()
    assert service.drafts.list_manage_dates() == ["20260226"]
    assert window.stock_search_input.isEnabled() is False


def test_delete_history_action_clears_current_date_without_switching(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service, auto_update_stock_basic=False)
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_select_history_date_for_delete", lambda dates: "20260225")
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window.delete_history_action.trigger()

    assert service.drafts.list_manage_dates() == []
    assert "20260225" in [window.date_combo.itemData(index, Qt.UserRole) for index in range(window.date_combo.count())]
    assert window.draft.manage_date == "20260225"
    assert window.draft.export_state == "empty"
    assert window.tabs.tabText(0) == "全部 0"
    assert "无数据" in window.draft_summary_label.text()


def test_delete_history_dialog_uses_project_combo_style(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service, auto_update_stock_basic=False)
    qtbot.addWidget(window)
    captured = {}

    def fake_exec(dialog):
        captured["combo"] = dialog.findChild(AutoWidthComboBox, "delete_history_date_combo")
        return main_window_module.QDialog.Rejected

    monkeypatch.setattr(main_window_module.QDialog, "exec", fake_exec)

    assert window._select_history_date_for_delete(["20260225"]) is None
    assert isinstance(captured["combo"], AutoWidthComboBox)
    assert captured["combo"].itemText(0) == "20260225 周三"


def test_settings_button_saves_config_and_tushare_token(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    user_dir = tmp_path / "user_data"
    monkeypatch.setattr(main_window_module, "get_user_data_dir", lambda: user_dir)

    class FakeSettingsDialog:
        def __init__(self, config, parent=None, *, token_hint=""):
            self.config = config
            self.token_hint = token_hint

        def exec(self):
            return main_window_module.QDialog.Accepted

        def to_config(self, base_config):
            return AppConfig(
                ptrade_data_dir="/new/ptrade",
                order_data_dir="/new/order",
                last_opened_manage_date=base_config.last_opened_manage_date,
            )

        def token_text(self):
            return "saved-token"

    monkeypatch.setattr(main_window_module, "SettingsDialog", FakeSettingsDialog)
    window = MainWindow(draft, service, auto_update_stock_basic=False)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_button, Qt.LeftButton)

    saved = load_config(user_dir)
    assert saved.ptrade_data_dir == "/new/ptrade"
    assert saved.order_data_dir == "/new/order"
    assert (user_dir / ".env").read_text(encoding="utf-8") == "TUSHARE_TOKEN=saved-token\n"
    assert service.config.ptrade_data_dir == "/new/ptrade"
    assert "目录设置已保存" in window.status_label.text()
