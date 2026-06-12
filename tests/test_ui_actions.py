from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGroupBox, QLabel, QMessageBox

from ptrade_order_tool.ui.main_window import MainWindow, StatusLabel
from ptrade_order_tool.ui.styles import APP_STYLESHEET
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.stock_card import StockCard
from tests.test_app_service_actions import make_service


def test_confirm_button_updates_database(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    draft = service.load_draft("20260225")
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    qtbot.mouseClick(row.confirm_button, Qt.LeftButton)

    updated_order = next(
        order
        for stock in service.load_draft("20260225").stocks
        for order in stock.orders
        if order.id == order_id
    )
    assert updated_order.confirmed is True
    assert "订单已确认" in window.status_label.text()


def test_delete_button_removes_order_from_database(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    draft = service.load_draft("20260225")
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    qtbot.mouseClick(row.delete_button, Qt.LeftButton)

    assert all(order.id != order_id for stock in service.load_draft("20260225").stocks for order in stock.orders)
    assert "订单已删除" in window.status_label.text()


def test_add_order_button_creates_unconfirmed_order(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    button = window.findChild(type(window.export_button), "add_order_buy_limit_002153.SZ")

    assert button.text() == "+"
    qtbot.mouseClick(button, Qt.LeftButton)

    orders = [
        order
        for stock in service.load_draft("20260225").stocks
        if stock.ts_code == "002153.SZ"
        for order in stock.orders
    ]
    assert any(order.order_type == "buy_limit" and not order.confirmed for order in orders)
    assert "已新增订单" in window.status_label.text()


def test_locate_unconfirmed_button_jumps_to_first_pending_order(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.locate_unconfirmed_button, Qt.LeftButton)

    assert window.tabs.currentIndex() == 0
    assert "已定位待确认: 300162.SZ 雷曼光电" in window.status_label.text()
    assert window.locate_unconfirmed_button.isHidden() is False


def test_locate_unconfirmed_button_is_disabled_without_pending_orders(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    assert window.locate_unconfirmed_button.isEnabled() is False

    service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    window.set_draft(service.load_draft(draft.manage_date))

    assert window.locate_unconfirmed_button.isEnabled() is True


def test_compact_action_buttons_have_labels_and_tooltips(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    assert window.undo_delete_button.text() == "撤销"
    assert window.undo_delete_button.toolTip() == "撤销最近一次删除"
    assert window.locate_unconfirmed_button.text() == "定位"
    assert window.locate_unconfirmed_button.toolTip() == "定位第一条未确认订单"


def test_clickable_buttons_use_pointing_hand_cursor(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft(draft.manage_date), service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    assert window.locate_unconfirmed_button.cursor().shape() == Qt.PointingHandCursor
    assert window.check_export_button.cursor().shape() == Qt.PointingHandCursor
    assert row.confirm_button.cursor().shape() == Qt.PointingHandCursor


def test_state_buttons_have_explicit_hover_styles():
    assert 'QPushButton#locate_unconfirmed_button:enabled:hover' in APP_STYLESHEET
    assert 'QPushButton#check_export_button[tone="blocker"]:hover' in APP_STYLESHEET
    assert 'QPushButton#check_export_button[tone="warning"]:hover' in APP_STYLESHEET
    assert 'QPushButton#check_export_button[tone="pending"]:hover' in APP_STYLESHEET
    assert 'QPushButton#order_confirm_button[status="pending"]:hover' in APP_STYLESHEET
    assert 'QPushButton#order_confirm_button[status="confirmed"]:hover' in APP_STYLESHEET


def test_sell_order_groups_use_neutral_body_background():
    assert 'QWidget#order_group_header[side="sell_profit"]' not in APP_STYLESHEET
    assert 'QWidget#order_group_header[side="sell_loss"]' not in APP_STYLESHEET
    assert 'QGroupBox[side="sell_profit"] {\n    background:' not in APP_STYLESHEET
    assert 'QGroupBox[side="sell_loss"] {\n    background:' not in APP_STYLESHEET


def test_status_label_elides_long_process_message(qtbot):
    label = StatusLabel()
    qtbot.addWidget(label)
    label.resize(80, 24)
    label.setText("这是一个很长的过程信息，需要在界面顶部用省略号显示")

    assert label.text().endswith("…") or label.text().endswith("...")
    assert label.toolTip() == "这是一个很长的过程信息，需要在界面顶部用省略号显示"

    label.resize(1000, 24)
    label.setText("短信息")

    assert label.text() == "短信息"
    assert label.toolTip() == ""


def test_search_add_stock_creates_opening_card(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("600000")
    qtbot.mouseClick(window.add_stock_button, Qt.LeftButton)

    assert any(stock.ts_code == "600000.SH" for stock in service.load_draft("20260225").stocks)
    headers = [label.text() for label in window.findChildren(type(window.total_label), "stock_card_header")]
    assert any("浦发银行" in header for header in headers)
    assert "已添加股票" in window.status_label.text()
    assert window.tabs.currentIndex() == 1


def test_add_stock_button_enabled_only_for_unique_candidate(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            if query == "600000":
                return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("6000")
    assert window.add_stock_button.isEnabled() is False

    window.stock_search_input.setText("600000")
    assert window.add_stock_button.isEnabled() is True


def test_add_stock_button_requires_exact_unique_input(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            normalized = query.strip().upper()
            if normalized in {"600000", "600000.SH"}:
                return {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}
            return None

        def search_stocks(self, query: str, limit: int = 20):
            if query == "浦发银行":
                return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("6000")
    assert window.add_stock_button.isEnabled() is False

    for text in ("600000", "600000.SH", "600000.sh", "浦发银行", "600000.SH 浦发银行"):
        window.stock_search_input.setText(text)
        assert window.add_stock_button.isEnabled() is True


def test_stock_search_return_key_adds_stock(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("600000")
    qtbot.keyClick(window.stock_search_input, Qt.Key_Return)

    assert any(stock.ts_code == "600000.SH" for stock in service.load_draft("20260225").stocks)


def test_search_add_stock_supports_search_matcher(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("pfyh")
    assert window.add_stock_button.isEnabled() is False
    window._handle_stock_candidate_activated("600000.SH 浦发银行")
    qtbot.mouseClick(window.add_stock_button, Qt.LeftButton)

    assert any(stock.ts_code == "600000.SH" for stock in service.load_draft("20260225").stocks)


def test_stock_search_updates_inline_candidates(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("6000")

    assert window.stock_candidate_popup.count() == 2
    assert window.stock_candidate_popup.item(0).text().startswith("600000.SH")
    assert window.stock_candidate_popup.currentRow() == -1
    assert window.stock_search_input.text() == "6000"

    window._handle_stock_candidate_activated(window.stock_candidate_popup.item(0).text())

    assert window.stock_search_input.text() == "600000.SH 浦发银行"
    assert window.add_stock_button.isEnabled() is True
    assert all(stock.ts_code != "600000.SH" for stock in service.load_draft("20260225").stocks)


def test_stock_search_does_not_autofill_while_typing_or_deleting(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    window.stock_search_input.setFocus()

    qtbot.keyClicks(window.stock_search_input, "p")
    assert window.stock_search_input.text() == "p"
    assert window.add_stock_button.isEnabled() is False

    qtbot.keyClick(window.stock_search_input, Qt.Key_Backspace)
    assert window.stock_search_input.text() == ""
    assert window.add_stock_button.isEnabled() is False


def test_stock_search_keyboard_highlights_first_candidate_then_confirms(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    window.stock_search_input.setFocus()
    window.stock_search_input.setText("6000")

    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    assert window.stock_search_input.text() == "6000"
    assert window.stock_candidate_popup.currentRow() == 0
    qtbot.keyClick(window.stock_search_input, Qt.Key_Return)

    assert window.stock_search_input.text() == "600000.SH 浦发银行"
    assert window.add_stock_button.isEnabled() is True
    assert window.stock_candidate_popup.isVisible() is False
    assert all(stock.ts_code != "600000.SH" for stock in service.load_draft("20260225").stocks)


def test_stock_search_keyboard_moves_between_candidates(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    window.stock_search_input.setFocus()
    window.stock_search_input.setText("6000")

    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    assert window.stock_search_input.text() == "6000"
    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    assert window.stock_search_input.text() == "6000"
    assert window.stock_candidate_popup.currentRow() == 1
    qtbot.keyClick(window.stock_search_input, Qt.Key_Return)

    assert window.stock_search_input.text() == "600010.SH 包钢股份"
    assert window.add_stock_button.isEnabled() is True
    assert all(stock.ts_code != "600010.SH" for stock in service.load_draft("20260225").stocks)


def test_stock_search_keyboard_navigation_resets_between_queries(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    window.stock_search_input.setFocus()

    window.stock_search_input.setText("6000")
    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    qtbot.keyClick(window.stock_search_input, Qt.Key_Return)
    assert window.stock_search_input.text() == "600000.SH 浦发银行"

    window.stock_search_input.setText("6000")
    assert window.stock_candidate_popup.currentRow() == -1
    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    qtbot.keyClick(window.stock_search_input, Qt.Key_Down)
    qtbot.keyClick(window.stock_search_input, Qt.Key_Return)

    assert window.stock_search_input.text() == "600010.SH 包钢股份"


def test_stock_search_mouse_hover_highlights_without_confirming(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
                {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
            ]

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    window.stock_search_input.setFocus()
    window.stock_search_input.setText("6000")

    item = window.stock_candidate_popup.item(1)
    window.stock_candidate_popup.setCurrentItem(item)

    assert window.stock_candidate_popup.currentRow() == 1
    assert window.stock_search_input.text() == "6000"
    assert window.add_stock_button.isEnabled() is False

    window._handle_stock_candidate_activated(item.text())

    assert window.stock_search_input.text() == "600010.SH 包钢股份"
    assert window.stock_candidate_popup.isVisible() is False


def test_search_add_stock_selects_from_multiple_candidates(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    candidates = [
        {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"},
        {"ts_code": "600010.SH", "symbol": "600010", "name": "包钢股份"},
    ]

    class SearchMatcher:
        def resolve_stock(self, query: str):
            return None

        def search_stocks(self, query: str, limit: int = 20):
            return candidates

    service.stock_matcher = SearchMatcher()
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_search_input.setText("6000")
    window._handle_stock_candidate_activated("600010.SH  包钢股份")

    assert window.stock_search_input.text() == "600010.SH 包钢股份"
    assert window.add_stock_button.isEnabled() is True
    assert all(stock.ts_code != "600010.SH" for stock in service.load_draft("20260225").stocks)


def test_more_menu_contains_only_low_frequency_actions(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    action_texts = [action.text() for action in window.more_menu.actions()]

    assert "设置目录及Token" in action_texts
    assert "导入盘后JSON" in action_texts
    assert "重新导入" not in action_texts
    assert "撤销删除" not in action_texts
    assert "定位未确认" not in action_texts
    assert "删除历史数据" in action_texts


def test_undo_delete_restores_order(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    qtbot.mouseClick(row.delete_button, Qt.LeftButton)
    qtbot.mouseClick(window.undo_delete_button, Qt.LeftButton)

    assert any(order.order_type == "buy_limit" for stock in service.load_draft("20260225").stocks for order in stock.orders)
    assert "已撤销删除" in window.status_label.text()


def test_export_button_writes_order_json(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    qtbot.mouseClick(window.export_button, Qt.LeftButton)

    assert (order_dir / "20260225.json").exists()
    assert window.status_label.text().startswith("导出完成:")
    assert window.status_label.toolTip() == f"导出完成: {order_dir / '20260225.json'}"


def test_open_export_dir_button_opens_configured_directory(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    opened = []
    monkeypatch.setattr(
        "ptrade_order_tool.ui.main_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    window.open_export_dir_action.trigger()

    assert opened == [str(order_dir)]
    assert window.status_label.text().startswith("已打开导出目录:")
    assert window.status_label.toolTip() == f"已打开导出目录: {order_dir}"


def test_delete_stock_card_requires_confirmation_and_supports_undo(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    card = next(card for card in window.findChildren(StockCard) if card.stock.ts_code == "002153.SZ")

    qtbot.mouseClick(card.delete_stock_button, Qt.LeftButton)

    assert all(stock.ts_code != "002153.SZ" for stock in service.load_draft("20260225").stocks)
    assert "股票已删除" in window.status_label.text()

    qtbot.mouseClick(window.undo_delete_button, Qt.LeftButton)

    assert any(stock.ts_code == "002153.SZ" for stock in service.load_draft("20260225").stocks)
    assert "已撤销删除" in window.status_label.text()


def test_export_button_shows_structured_blockers(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append((title, text)))

    qtbot.mouseClick(window.export_button, Qt.LeftButton)

    assert window.export_button.isEnabled() is False
    assert messages == []


def test_check_export_button_reports_pending_and_blockers(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_export_check_dialog",
        lambda pending, blockers, warnings: captured.append((pending, blockers, warnings)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    assert captured
    pending, blockers, warnings = captured[0]
    assert pending == ["002153.SZ 石基信息 待确认 1 条"]
    assert blockers == ["002153.SZ 石基信息 存在未确认订单"]
    assert warnings == []
    assert "导出检查: 1 个阻断项" in window.status_label.text()
    assert window.check_export_button.property("tone") == "blocker"
    assert window.export_button.isEnabled() is False


def test_check_export_button_reports_warnings_without_blockers(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    profit_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1400)
    service.update_and_confirm_order(profit_id, price=Decimal("12.65"), shares=1400, order_type="sell_profit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_export_check_dialog",
        lambda pending, blockers, warnings: captured.append((pending, blockers, warnings)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    pending, blockers, warnings = captured[0]
    assert pending == []
    assert blockers == []
    assert any("止盈合计 1400 不等于可卖数量" in item for item in warnings)
    assert "导出检查: " in window.status_label.text()
    assert "个提醒项" in window.status_label.text()
    assert window.check_export_button.property("tone") == "warning"
    assert window.export_button.isEnabled() is True


def test_check_export_button_reports_clean_draft(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    buy_id = service.drafts.add_order(draft.manage_date, "600000.SH", "浦发银行", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(buy_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_export_check_dialog",
        lambda pending, blockers, warnings: captured.append((pending, blockers, warnings)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    assert captured == [([], [], [])]
    assert "导出检查通过" in window.status_label.text()
    assert window.check_export_button.property("tone") == "clean"
    assert window.export_button.isEnabled() is True


def test_editing_confirmed_order_marks_it_unconfirmed(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    rows = [row for row in window.findChildren(OrderRow) if row.order.id == order_id]

    rows[0].price_input.set_value(Decimal("11.5"))

    updated_rows = [row for row in window.findChildren(OrderRow) if row.order.id == order_id]
    updated_order = next(
        order
        for stock in service.load_draft("20260225").stocks
        for order in stock.orders
        if order.id == order_id
    )
    validation = service.validate_draft_for_export("20260225")

    assert updated_order.confirmed is False
    assert updated_order.price == Decimal("11.5")
    assert any(label.objectName() == "order_status_indicator" and label.toolTip() == "未确认" for label in window.findChildren(QLabel))
    assert all(row.price_input.value() == Decimal("11.5") for row in updated_rows)
    assert validation.can_export is False
    assert "订单已修改，需重新确认" in window.status_label.text()


def test_changing_order_type_moves_order_group(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)
    sell_profit_index = row.type_combo.findData("sell_profit")

    row.type_combo.setCurrentIndex(sell_profit_index)

    updated_order = next(
        order
        for stock in service.load_draft("20260225").stocks
        for order in stock.orders
        if order.id == order_id
    )

    assert updated_order.order_type == "sell_profit"
    assert updated_order.confirmed is False
    assert any(label.objectName() == "order_group_title_sell_profit" and "止盈  1" in label.text() for label in window.findChildren(type(window.total_label)))


def test_export_button_refreshes_after_overwrite(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    service.update_and_confirm_order(order_id, price=Decimal("11.4"), shares=1400, order_type="buy_limit")
    (order_dir / "20260225.json").write_text("{}", encoding="utf-8")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    qtbot.mouseClick(window.export_button, Qt.LeftButton)

    assert service.load_draft("20260225").export_state == "exported"
    assert window.draft.export_state == "exported"
    assert window.status_label.text().startswith("导出完成:")
    assert window.status_label.toolTip() == f"导出完成: {order_dir / '20260225.json'}"


def test_manual_import_button_imports_selected_json(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    manual_path = tmp_path / "ptrade_data" / "20260225.json"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(manual_path), ""))

    qtbot.mouseClick(window.manual_import_button, Qt.LeftButton)

    assert window.draft.manage_date == "20260225"
    assert "导入完成" in window.status_label.text()


def test_reimport_button_overwrites_current_draft(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    qtbot.mouseClick(window.reimport_button, Qt.LeftButton)

    assert all(order.id != order_id for stock in service.load_draft("20260225").stocks for order in stock.orders)
    assert "重新导入完成" in window.status_label.text()
