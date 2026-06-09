from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

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
    assert "导出完成" in window.status_label.text()


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
    assert "导出完成" in window.status_label.text()


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
