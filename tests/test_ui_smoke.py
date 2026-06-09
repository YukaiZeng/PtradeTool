from pathlib import Path
from decimal import Decimal

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.stock_card import StockCard
from tests.test_ptrade_importer import FakeStockMatcher


PTRADER_FIXTURE = Path(__file__).parent / "fixtures" / "ptrade_20260225.json"


def make_fixture_draft(sqlite_conn):
    initialize_schema(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    store = DraftStore(sqlite_conn)
    return store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )


def test_main_window_renders_account_and_stock_cards(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)

    assert "88381.86" in window.total_label.text()
    assert "55020.0" in window.stock_value_label.text()
    assert "33361.86" in window.cash_label.text()
    assert window.findChildren(StockCard)
    assert window.findChildren(type(window.total_label), "stock_card_header")


def test_main_window_filters_out_standard_bond(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)

    headers = [label.text() for label in window.findChildren(type(window.total_label), "stock_card_header")]
    joined = "\n".join(headers)
    assert "石基信息" in joined
    assert "雷曼光电" in joined
    assert "光线传媒" in joined
    assert "标准券" not in joined


def test_stock_update_button_states(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.set_stock_update_state("generate")
    assert window.stock_update_button.text() == "生成股票基础数据"
    assert window.stock_update_button.isEnabled() is True

    window.set_stock_update_state("updated_disabled")
    assert window.stock_update_button.text() == "已更新股票基础数据"
    assert window.stock_update_button.isEnabled() is False

    window.set_stock_update_state("update_enabled")
    assert window.stock_update_button.text() == "更新股票基础数据"
    assert window.stock_update_button.isEnabled() is True

    window.set_stock_update_state("update_disabled_non_trade_day")
    assert window.stock_update_button.text() == "更新股票基础数据"
    assert window.stock_update_button.isEnabled() is False


def test_auto_update_runs_when_stock_data_missing(qtbot, monkeypatch):
    started = []

    class FakeWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithResult = FakeSignal()
            self.failedWithMessage = FakeSignal()
            self.finished = FakeSignal()

        def isRunning(self):
            return False

        def start(self):
            started.append(True)

    class FakeSignal:
        def connect(self, callback):
            return None

    class FakeService:
        def stock_update_button_state(self, today):
            return "generate"

        def list_manage_dates(self):
            return []

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.StockUpdateWorker", FakeWorker)

    window = MainWindow(service=FakeService(), auto_update_stock_basic=True)
    qtbot.addWidget(window)

    assert started == [True]


def test_stock_card_shows_quantity_warning_and_order_status(qtbot, sqlite_conn):
    initialize_schema(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1400)
    store.confirm_order(order_id)
    window = MainWindow(store.load_draft("20260225"))
    qtbot.addWidget(window)

    warnings = [label.text() for label in window.findChildren(type(window.total_label), "stock_card_warning")]
    statuses = [row.status_label.text() for row in window.findChildren(OrderRow)]

    assert any("止盈合计 1400" in item for item in warnings)
    assert "已确认" in statuses
