from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QPushButton

from ptrade_order_tool.config import AppConfig
from ptrade_order_tool.config import load_config
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from ptrade_order_tool.ui import main_window as main_window_module
from ptrade_order_tool.ui.main_window import MainWindow
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

    assert service.list_manage_dates() == ["20260226", "20260225"]


def test_date_combo_switches_to_historical_read_only(qtbot, sqlite_conn, tmp_path):
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

    window.date_combo.setCurrentText("20260225")

    assert window.draft.manage_date == "20260225"
    assert window.draft.read_only is True
    assert "历史日期只读" in window.status_label.text()


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
    window = MainWindow(service.load_draft("20260225"), service, auto_update_stock_basic=False)
    qtbot.addWidget(window)

    rows = window.findChildren(OrderRow)
    add_buttons = [button for card in window.findChildren(StockCard) for button in card.findChildren(type(window.export_button)) if button.objectName().startswith("add_order_")]

    assert window.stock_search_input.isEnabled() is False
    assert window.add_stock_button.isEnabled() is False
    assert window.reimport_button.isEnabled() is False
    assert all(not row.confirm_button.isEnabled() for row in rows)
    assert all(not row.delete_button.isEnabled() for row in rows)
    assert all(not button.isEnabled() for button in add_buttons)


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
