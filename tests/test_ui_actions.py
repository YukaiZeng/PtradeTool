import json
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QGroupBox, QLabel, QMessageBox, QWidget

from ptrade_order_tool.ui import order_row as order_row_module
from ptrade_order_tool.ui import stock_card as stock_card_module
from ptrade_order_tool.ui.main_window import MainWindow, StatusLabel
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.styles import APP_STYLESHEET, _preferred_ui_font_family
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


def test_confirm_preserves_added_share_digit_width(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    row.shares_input.add_high_digit()
    assert row.shares_input.text() == "01400"

    qtbot.mouseClick(row.confirm_button, Qt.LeftButton)

    updated_rows = [row for row in window.findChildren(OrderRow) if row.order.id == order_id]
    assert all(row.shares_input.text() == "01400" for row in updated_rows)
    assert all(row.shares_input.integer_width() == 5 for row in updated_rows)


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


def test_order_add_confirm_delete_refreshes_only_affected_card(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    untouched_card = window._stock_cards_by_code["300162.SZ"]
    full_render_calls = []
    monkeypatch.setattr(window, "_render_stock_cards_or_empty", lambda draft: full_render_calls.append(draft))

    qtbot.mouseClick(window.findChild(type(window.export_button), "add_order_buy_limit_002153.SZ"), Qt.LeftButton)
    row = next(row for row in window.findChildren(OrderRow) if row.order.order_type == "buy_limit")
    order_id = row.order.id
    row.price_input.set_cursor_index(0)
    row.price_input.show_digit_menu()
    popup = row.price_input._active_menu

    qtbot.mouseClick(row.confirm_button, Qt.LeftButton)
    confirmed_row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)
    qtbot.mouseClick(confirmed_row.delete_button, Qt.LeftButton)

    assert full_render_calls == []
    assert window._stock_cards_by_code["300162.SZ"] is untouched_card
    assert popup is not None and not popup.isVisible()


def test_order_changes_preserve_selected_stock_card_position(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.resize(900, 460)
    window.show()
    qtbot.waitExposed(window)

    window.stock_jump_combo.setCurrentIndex(1)
    window.stock_jump_combo.activated.emit(1)
    qtbot.wait(20)
    selected_card = window._stock_cards_by_code["300162.SZ"]
    assert window.stock_jump_combo.currentData(Qt.UserRole) == "300162.SZ"
    assert selected_card.mapTo(window.stock_scroll.viewport(), QPoint(0, 0)).y() == 0

    add_order_button = window.findChild(type(window.export_button), "add_order_buy_limit_300162.SZ")
    qtbot.mouseClick(add_order_button, Qt.LeftButton)
    qtbot.wait(250)

    anchor_y_after = window._stock_cards_by_code["300162.SZ"].mapTo(
        window.stock_scroll.viewport(),
        QPoint(0, 0),
    ).y()
    assert anchor_y_after == 0
    assert window.stock_jump_combo.currentData(Qt.UserRole) == "300162.SZ"

    added_row = next(row for row in window.findChildren(OrderRow) if row.order.order_type == "buy_limit")
    order_id = added_row.order.id
    qtbot.mouseClick(added_row.confirm_button, Qt.LeftButton)
    qtbot.wait(250)

    anchor_y_after_confirm = window._stock_cards_by_code["300162.SZ"].mapTo(
        window.stock_scroll.viewport(),
        QPoint(0, 0),
    ).y()
    assert anchor_y_after_confirm == 0
    assert window.stock_jump_combo.currentData(Qt.UserRole) == "300162.SZ"

    confirmed_row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)
    qtbot.mouseClick(confirmed_row.delete_button, Qt.LeftButton)
    qtbot.wait(250)

    anchor_y_after_delete = window._stock_cards_by_code["300162.SZ"].mapTo(
        window.stock_scroll.viewport(),
        QPoint(0, 0),
    ).y()
    assert anchor_y_after_delete == 0
    assert window.stock_jump_combo.currentData(Qt.UserRole) == "300162.SZ"


def test_deleting_selected_stock_keeps_viewport_and_clears_stock_jump_selection(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.resize(900, 460)
    window.show()
    qtbot.waitExposed(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window.stock_jump_combo.setCurrentIndex(2)
    window.stock_jump_combo.activated.emit(2)
    qtbot.wait(20)
    scroll_bar = window.stock_scroll.verticalScrollBar()
    scroll_value_before = scroll_bar.value()
    scroll_values = []
    scroll_bar.valueChanged.connect(scroll_values.append)
    selected_card = window._stock_cards_by_code["300251.SZ"]
    qtbot.mouseClick(selected_card.delete_stock_button, Qt.LeftButton)
    qtbot.wait(250)

    assert window.stock_jump_combo.currentIndex() == -1
    assert [window.stock_jump_combo.itemData(index, Qt.UserRole) for index in range(window.stock_jump_combo.count())] == [
        "002153.SZ",
        "300162.SZ",
    ]
    assert scroll_bar.value() == scroll_value_before
    assert scroll_values == []

    remaining_card = window._stock_cards_by_code["300162.SZ"]
    scroll_bar.setValue(remaining_card.y())
    scroll_value_before = scroll_bar.value()
    scroll_values.clear()
    qtbot.mouseClick(window.findChild(type(window.export_button), "add_order_buy_limit_300162.SZ"), Qt.LeftButton)
    qtbot.wait(250)

    assert scroll_bar.value() == scroll_value_before
    assert scroll_values == []


def test_switching_draft_defaults_stock_jump_to_first_visible_stock_when_selection_is_absent(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    window.stock_jump_combo.setCurrentIndex(1)
    replacement_draft, _ = service.delete_stock_with_snapshot(draft.manage_date, "300162.SZ")
    window.set_draft(replacement_draft, default_to_holding=True)

    assert window.stock_jump_combo.currentIndex() == 0
    assert window.stock_jump_combo.currentData(Qt.UserRole) == "002153.SZ"


def test_order_actions_do_not_show_transient_top_level_widgets(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    class TopLevelShowRecorder(QObject):
        def __init__(self, allowed):
            super().__init__()
            self.allowed = set(allowed)
            self.shown = []
            self.parentless_windows = []

        def eventFilter(self, watched, event):  # noqa: N802
            if (
                event.type() == QEvent.Show
                and isinstance(watched, QWidget)
                and watched.isWindow()
                and watched not in self.allowed
            ):
                self.shown.append(watched.objectName() or watched.__class__.__name__)
            if (
                event.type() in {QEvent.ParentChange, QEvent.WinIdChange}
                and isinstance(watched, QWidget)
                and watched.isWindow()
                and watched.parentWidget() is None
                and watched not in self.allowed
            ):
                self.parentless_windows.append(watched.objectName() or watched.__class__.__name__)
            return False

    app = QApplication.instance()
    recorder = TopLevelShowRecorder({window})
    app.installEventFilter(recorder)
    try:
        qtbot.mouseClick(window.findChild(type(window.export_button), "add_order_buy_limit_002153.SZ"), Qt.LeftButton)
        row = next(row for row in window.findChildren(OrderRow) if row.order.order_type == "buy_limit")
        order_id = row.order.id
        qtbot.mouseClick(row.confirm_button, Qt.LeftButton)
        confirmed_row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)
        qtbot.mouseClick(confirmed_row.delete_button, Qt.LeftButton)
        qtbot.wait(10)
    finally:
        app.removeEventFilter(recorder)

    assert recorder.shown == []
    assert recorder.parentless_windows == []


def test_rebuilt_stock_cards_construct_children_with_parents(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)

    def parent_required(widget_type):
        class ParentRequired(widget_type):
            def __init__(self, *args, parent=None, **kwargs):
                assert parent is not None, f"{widget_type.__name__} was created without a parent"
                super().__init__(*args, parent=parent, **kwargs)

        return ParentRequired

    for module, widget_names in (
        (order_row_module, ("QWidget", "QComboBox", "QLabel", "QPushButton", "DigitInput")),
        (stock_card_module, ("QWidget", "QLabel", "QPushButton", "MiniKLine", "EmbeddedOrderGroup", "OrderRow")),
    ):
        for widget_name in widget_names:
            monkeypatch.setattr(module, widget_name, parent_required(getattr(module, widget_name)))

    StockCard(draft.stocks[0], parent=QWidget())


def test_locate_unconfirmed_button_jumps_to_first_pending_order(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.locate_unconfirmed_button, Qt.LeftButton)

    assert window.tabs.currentIndex() == 0
    assert "已定位需处理: 300162.SZ 雷曼光电" in window.status_label.text()
    assert window.locate_unconfirmed_button.isHidden() is False


def test_locate_button_jumps_to_first_blocking_invalid_order(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("0"), 1000)
    service.drafts.confirm_order(order_id)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.locate_unconfirmed_button, Qt.LeftButton)

    assert window.tabs.currentIndex() == 0
    assert "已定位需处理: 300162.SZ 雷曼光电" in window.status_label.text()
    assert window.locate_unconfirmed_button.isEnabled() is True


def test_locate_button_uses_visible_stock_order_for_pending_or_blocking(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    blocker_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("0"), 1000)
    service.drafts.confirm_order(blocker_id)
    service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.locate_unconfirmed_button, Qt.LeftButton)

    assert "已定位需处理: 002153.SZ 石基信息" in window.status_label.text()


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
    assert window.locate_unconfirmed_button.toolTip() == "定位第一条未确认或阻断项订单"


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
    assert 'QPushButton#check_export_button[tone="pending"]:hover' in APP_STYLESHEET
    assert 'QPushButton#order_confirm_button[status="pending"]:hover' in APP_STYLESHEET
    assert 'QPushButton#order_confirm_button[status="confirmed"]:hover' in APP_STYLESHEET
    assert 'status="inherited"' not in APP_STYLESHEET


def test_pending_check_color_is_orange():
    assert 'QPushButton#check_export_button[tone="pending"] {\n    background: #fff7ed;' in APP_STYLESHEET
    assert 'QWidget#export_check_section[tone="pending"] {\n    background: #fff7ed;' in APP_STYLESHEET


def test_order_row_leading_bar_stays_neutral():
    assert 'QWidget#order_row[side="buy"]' not in APP_STYLESHEET
    assert 'QWidget#order_row[side="sell_profit"]' not in APP_STYLESHEET
    assert 'QWidget#order_row[side="sell_loss"]' not in APP_STYLESHEET


def test_stock_card_warning_uses_blue_colors():
    assert 'QWidget#stock_card_warning_box {\n    background: #eff6ff;' in APP_STYLESHEET
    assert 'border: 1px solid #bfdbfe;' in APP_STYLESHEET
    assert 'QLabel#stock_card_warning {\n    color: #1d4ed8;' in APP_STYLESHEET


def test_preferred_ui_font_family_prioritizes_cjk_friendly_fonts():
    assert _preferred_ui_font_family(["Microsoft YaHei UI", "Arial"]) == "Microsoft YaHei UI"
    assert _preferred_ui_font_family(["PingFang SC", "Arial"]) == "PingFang SC"
    assert _preferred_ui_font_family(["Arial"]) == "Arial"
    assert "font-family" not in APP_STYLESHEET


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
    assert "同步JSON到界面" in action_texts
    assert "重新导入" not in action_texts
    assert "撤销删除" not in action_texts
    assert "定位未确认" not in action_texts
    assert "删除历史数据" in action_texts


def test_sync_json_action_is_enabled_only_when_json_differs(qtbot, sqlite_conn, tmp_path):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    assert window.sync_json_action.isEnabled() is False

    (order_dir / "20260225.json").write_text(
        json.dumps({"002153.SZ": {"stock_name": "石基信息", "buy_limit": [{"price": 11.4, "shares": 1400}]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    window._refresh_sync_json_action()

    assert window.sync_json_action.isEnabled() is True
    assert "导出 JSON" in window.sync_json_action.toolTip()


def test_sync_json_action_updates_ui_and_confirms_orders(qtbot, sqlite_conn, tmp_path):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_limit", Decimal("8.8"), 1000)
    (order_dir / "20260225.json").write_text(
        json.dumps({"002153.SZ": {"stock_name": "石基信息", "buy_limit": [{"price": 11.4, "shares": 1400}]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    window.sync_json_action.trigger()

    synced = service.load_draft("20260225")
    shiji = next(stock for stock in synced.stocks if stock.ts_code == "002153.SZ")
    leiman = next(stock for stock in synced.stocks if stock.ts_code == "300162.SZ")
    assert [(order.order_type, order.price, order.shares, order.confirmed) for order in shiji.orders] == [
        ("buy_limit", Decimal("11.4"), 1400, True)
    ]
    assert leiman.orders == []
    assert window.sync_json_action.isEnabled() is False
    assert "已同步JSON到界面" in window.status_label.text()


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

    assert [Path(path) for path in opened] == [order_dir]
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
    blocker_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_loss", Decimal("0"), 100)
    service.update_and_confirm_order(blocker_id, price=Decimal("0"), shares=100, order_type="sell_loss")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_export_check_dialog",
        lambda pending, blockers: captured.append((pending, blockers)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    assert captured
    pending, blockers = captured[0]
    assert pending == ["002153.SZ 石基信息 待确认 1 条"]
    assert blockers == ["002153.SZ 石基信息 订单价格必须大于0"]
    assert "导出前检查: 1 个阻断项，1 个待确认项" in window.status_label.text()
    assert window.check_export_button.property("tone") == "blocker"
    assert window.check_export_button.toolTip() == "1 个阻断项，1 个待确认项"
    assert window.export_button.isEnabled() is False


def test_check_export_button_uses_pending_tone_when_only_pending_blocks_export(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)

    assert window.check_export_button.property("tone") == "pending"
    assert window.check_export_button.toolTip() == "1 个待确认项"


def test_export_check_dialog_section_order(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    sections = []

    def fake_section(title, items, tone):
        sections.append((title, tone))
        return QLabel(title)

    monkeypatch.setattr(window, "_make_export_check_section", fake_section)

    class FakeDialog(QDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def exec(self):
            return 0

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.QDialog", FakeDialog)

    window._show_export_check_dialog(["pending"], ["blocker"])

    assert sections == [("阻断项", "blocker"), ("待确认", "pending")]


def test_export_check_summary_copy_is_explicit(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)

    assert window._check_summary_text(["pending"], ["blocker"]) == "导出前需处理：1 个阻断项、1 个待确认项"
    assert window._check_summary_text([], []) == "导出前检查通过，可以导出"


def test_check_export_button_ignores_card_warnings_without_blockers(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    profit_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1400)
    service.update_and_confirm_order(profit_id, price=Decimal("12.65"), shares=1400, order_type="sell_profit")
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_export_check_dialog",
        lambda pending, blockers: captured.append((pending, blockers)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    pending, blockers = captured[0]
    assert pending == []
    assert blockers == []
    card_warnings = [label.text() for label in window.findChildren(QLabel, "stock_card_warning")]
    assert any("止盈合计 1,400，不等于持仓 2,800" in item for item in card_warnings)
    assert "导出前检查通过" in window.status_label.text()
    assert window.check_export_button.property("tone") == "clean"
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
        lambda pending, blockers: captured.append((pending, blockers)),
    )

    qtbot.mouseClick(window.check_export_button, Qt.LeftButton)

    assert captured == [([], [])]
    assert "导出前检查通过" in window.status_label.text()
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


def test_manual_import_action_imports_selected_json(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    manual_path = tmp_path / "ptrade_data" / "20260225.json"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(manual_path), ""))

    window.manual_import_action.trigger()

    assert window.draft.manage_date == "20260225"
    assert "导入完成" in window.status_label.text()
