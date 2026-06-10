from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGroupBox, QMessageBox

from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.order_row import OrderRow
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
    qtbot.mouseClick(window.add_stock_button, Qt.LeftButton)

    assert any(stock.ts_code == "600000.SH" for stock in service.load_draft("20260225").stocks)


def test_search_add_stock_selects_from_multiple_candidates(qtbot, sqlite_conn, tmp_path, monkeypatch):
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
    monkeypatch.setattr(window, "_select_stock_candidate", lambda items: items[1])

    window.stock_search_input.setText("6000")
    qtbot.mouseClick(window.add_stock_button, Qt.LeftButton)

    assert any(stock.ts_code == "600010.SH" and stock.stock_name == "包钢股份" for stock in service.load_draft("20260225").stocks)
    assert "已添加股票" in window.status_label.text()


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
    assert f"导出完成: {order_dir / '20260225.json'}" in window.status_label.text()


def test_open_export_dir_button_opens_configured_directory(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, order_dir = make_service(sqlite_conn, tmp_path)
    window = MainWindow(draft, service)
    qtbot.addWidget(window)
    opened = []
    monkeypatch.setattr(
        "ptrade_order_tool.ui.main_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    qtbot.mouseClick(window.open_export_dir_button, Qt.LeftButton)

    assert opened == [str(order_dir)]
    assert f"已打开导出目录: {order_dir}" in window.status_label.text()


def test_export_button_shows_structured_blockers(qtbot, sqlite_conn, tmp_path, monkeypatch):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft("20260225"), service)
    qtbot.addWidget(window)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: messages.append((title, text)))

    qtbot.mouseClick(window.export_button, Qt.LeftButton)

    assert messages
    assert messages[0][0] == "无法导出"
    assert "阻断项 1 个" in messages[0][1]
    assert "- 002153.SZ 石基信息 存在未确认订单" in messages[0][1]


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
    assert any(row.status_label.text() == "未确认" for row in updated_rows)
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
    assert any("止盈  1" in group.title() for group in window.findChildren(QGroupBox))


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
    assert f"导出完成: {order_dir / '20260225.json'}" in window.status_label.text()


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
