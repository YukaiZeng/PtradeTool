from pathlib import Path
from decimal import Decimal

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QWidget

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from ptrade_order_tool.ui.digit_input import DigitInput
from ptrade_order_tool.models import DailyQuote, OrderDraft, StockDraft
from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.order_row import OrderRow
from ptrade_order_tool.ui.stock_card import StockCard
from tests.test_app_service_actions import make_service
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

    assert "88,381.86" in window.total_label.text()
    assert "55,020.00" in window.stock_value_label.text()
    assert "33,361.86" in window.cash_label.text()
    assert window.opening_amount_label.text() == "开仓金额 0.00"
    assert not window.opening_amount_label.isHidden()
    assert "股票 3" in window.draft_summary_label.text()
    assert window.tabs.tabText(0) == "全部 3"
    assert window.tabs.tabText(1) == "开仓 0"
    assert window.tabs.tabText(2) == "持仓 3"
    assert window.tabs.currentIndex() == 2
    assert window.findChildren(StockCard)
    assert window.findChildren(type(window.total_label), "stock_card_header")
    assert window.findChildren(type(window.total_label), "stock_metric_chip")
    assert window.findChildren(type(window.total_label), "stock_type_badge")


def test_main_window_does_not_block_rendering_on_daily_quote_load(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    calls = []

    class BlockingQuoteService:
        def list_manage_dates(self):
            return [draft.manage_date]

        def stock_update_button_state(self, today):
            return "updated_disabled"

        def maintain_trade_calendar(self, **kwargs):
            return 0

        def load_daily_quotes(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {}

        def cached_daily_quotes(self, *args, **kwargs):
            return {}

        def has_daily_quote_cache(self, *args, **kwargs):
            return True

    window = MainWindow(draft, BlockingQuoteService(), auto_update_stock_basic=False)
    qtbot.addWidget(window)

    assert window.findChildren(StockCard)
    assert all(card.findChild(QWidget, "stock_daily_quote").isHidden() for card in window.findChildren(StockCard))
    assert calls == []


def test_main_window_reuses_loaded_daily_quotes_when_rerendering_draft(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    quote = DailyQuote(
        ts_code="002153.SZ",
        trade_date=draft.manage_date,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        pre_close=Decimal("10"),
        change=Decimal("1"),
        pct_chg=Decimal("10"),
        vol=Decimal("10000"),
        amount=Decimal("250000"),
    )
    cached_calls = []

    class QuoteService:
        def list_manage_dates(self):
            return [draft.manage_date]

        def stock_update_button_state(self, today):
            return "updated_disabled"

        def maintain_trade_calendar(self, **kwargs):
            return 0

        def cached_daily_quotes(self, *args, **kwargs):
            cached_calls.append((args, kwargs))
            return {"002153.SZ": quote}

        def has_daily_quote_cache(self, *args, **kwargs):
            return True

    window = MainWindow(draft, QuoteService(), auto_update_stock_basic=False)
    qtbot.addWidget(window)
    window._handle_daily_quotes_loaded(draft.manage_date, {"002153.SZ": quote})
    cached_calls.clear()

    window.set_draft(draft)

    assert cached_calls == []
    card = next(card for card in window.findChildren(StockCard) if card.stock.ts_code == "002153.SZ")
    assert card.findChild(QWidget, "stock_daily_quote").isHidden() is False


def test_main_window_merges_partial_daily_quote_updates(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    first_quote = DailyQuote(
        ts_code="002153.SZ",
        trade_date=draft.manage_date,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        pre_close=Decimal("10"),
        change=Decimal("1"),
        pct_chg=Decimal("10"),
        vol=Decimal("10000"),
        amount=Decimal("250000"),
    )
    second_quote = DailyQuote(
        ts_code="300162.SZ",
        trade_date=draft.manage_date,
        open=Decimal("8"),
        high=Decimal("9"),
        low=Decimal("7"),
        close=Decimal("8.5"),
        pre_close=Decimal("8"),
        change=Decimal("0.5"),
        pct_chg=Decimal("6.25"),
        vol=Decimal("12000"),
        amount=Decimal("300000"),
    )
    window = MainWindow(draft, auto_update_stock_basic=False)
    qtbot.addWidget(window)

    window._handle_daily_quotes_loaded(draft.manage_date, {"002153.SZ": first_quote})
    window._handle_daily_quotes_loaded(draft.manage_date, {"300162.SZ": second_quote})

    assert window._daily_quotes["002153.SZ"] is first_quote
    assert window._daily_quotes["300162.SZ"] is second_quote
    shiji_card = next(card for card in window.findChildren(StockCard) if card.stock.ts_code == "002153.SZ")
    leiman_card = next(card for card in window.findChildren(StockCard) if card.stock.ts_code == "300162.SZ")
    assert shiji_card.findChild(QWidget, "stock_daily_quote").isHidden() is False
    assert leiman_card.findChild(QWidget, "stock_daily_quote").isHidden() is False


def test_main_window_clears_active_digit_cursor_before_rerender(qtbot, sqlite_conn, tmp_path):
    service, draft, _ = make_service(sqlite_conn, tmp_path)
    order_id = service.drafts.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("11.4"), 1400)
    window = MainWindow(service.load_draft(draft.manage_date), service, auto_update_stock_basic=False)
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    row.price_input.set_cursor_index(0)
    assert DigitInput._active_cursor_input is row.price_input

    window.set_draft(service.load_draft(draft.manage_date))

    assert DigitInput._active_cursor_input is None


def test_stock_filter_tabs_reuse_single_card_set(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)

    cards = window.findChildren(StockCard)
    assert len(cards) == 3

    window.tabs.setCurrentIndex(1)
    assert all(card.isHidden() for card in cards)

    window.tabs.setCurrentIndex(2)
    assert all(not card.isHidden() for card in cards)


def test_stock_filter_tabs_fit_text_without_clipping(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)

    for index in range(3):
        text = window.tabs.tabText(index)
        button = window.tabs._buttons[index]
        assert button.width() >= button.fontMetrics().horizontalAdvance(text) + 24


def test_stock_card_uses_vertical_order_sections_with_add_button_in_header(qtbot):
    stock = StockDraft(
        ts_code="600000.SH",
        stock_name="浦发银行",
        is_holding=False,
        orders=[
            OrderDraft("buy_stop", Decimal("10.00"), 100),
            OrderDraft("buy_limit", Decimal("9.50"), 100),
            OrderDraft("sell_profit", Decimal("12.00"), 100),
            OrderDraft("sell_loss", Decimal("8.50"), 100),
        ],
    )
    card = StockCard(stock)
    qtbot.addWidget(card)
    card.show()
    qtbot.waitExposed(card)

    positions = {}
    for order_type in ("buy_stop", "buy_limit", "sell_profit", "sell_loss"):
        group = card.findChild(QGroupBox, f"order_group_{order_type}")
        assert group is not None
        index = card.orders_grid.indexOf(group)
        row, column, row_span, column_span = card.orders_grid.getItemPosition(index)
        positions[order_type] = (row, column, row_span, column_span)
        header = group.findChild(QWidget, "order_group_header")
        assert header.objectName() == "order_group_header"
        title_wrap = header.findChild(QWidget, "order_group_title_wrap")
        title = header.findChild(QLabel, f"order_group_title_{order_type}")
        add_button = header.findChild(QPushButton, f"add_order_{order_type}_600000.SH")
        assert title_wrap is not None
        assert title is not None
        assert add_button is not None
        assert add_button.text() == "+"
        assert header.layout().indexOf(title_wrap) == 0
        assert title_wrap.layout().indexOf(title) < title_wrap.layout().indexOf(add_button)
        assert header.y() == 0
        assert title.geometry().center().y() <= 12
        assert 8 <= title_wrap.geometry().left() <= 14
        assert add_button.width() <= 18
        assert add_button.height() <= 18
        assert add_button.styleSheet() == ""
        assert not any(button.text() == "新增" for button in header.findChildren(QPushButton))
        assert header.findChildren(QPushButton, "delete_stock_600000.SH") == []

    assert positions == {
        "buy_stop": (0, 0, 1, 1),
        "buy_limit": (1, 0, 1, 1),
        "sell_profit": (2, 0, 1, 1),
        "sell_loss": (3, 0, 1, 1),
    }
    assert card.delete_stock_button is not None


def test_stock_card_hides_empty_order_body_for_empty_sections(qtbot):
    stock = StockDraft(ts_code="600000.SH", stock_name="浦发银行", is_holding=False, orders=[])
    card = StockCard(stock)
    qtbot.addWidget(card)

    assert len(card.findChildren(QGroupBox)) == 4
    assert card.findChildren(QLabel, "empty_order_label") == []


def test_stock_card_shows_daily_quote_after_type_badge_without_growing_header(qtbot):
    stock = StockDraft(ts_code="600000.SH", stock_name="浦发银行", is_holding=False, orders=[])
    quote = DailyQuote(
        ts_code="600000.SH",
        trade_date="20260225",
        open=Decimal("10.00"),
        high=Decimal("10.80"),
        low=Decimal("9.80"),
        close=Decimal("10.50"),
        pre_close=Decimal("10.00"),
        change=Decimal("0.50"),
        pct_chg=Decimal("5.00"),
        vol=Decimal("10000"),
        amount=Decimal("250000"),
    )
    card = StockCard(stock, daily_quote=quote)
    qtbot.addWidget(card)
    card.show()
    qtbot.waitExposed(card)

    quote_widget = card.findChild(QWidget, "stock_daily_quote")
    price = card.findChild(QLabel, "stock_daily_price")
    pct = card.findChild(QLabel, "stock_daily_pct")
    amount = card.findChild(QLabel, "stock_daily_amount")
    kline = card.findChild(QWidget, "stock_daily_kline")

    assert quote_widget is not None
    assert quote_widget.isHidden() is False
    assert price.text() == "10.50"
    assert pct.text() == "+5.00%"
    assert pct.property("tone") == "up"
    assert amount.text() == "2.50亿"
    assert kline.height() <= quote_widget.height()
    assert quote_widget.height() <= card.type_badge.height() + 4


def test_stock_card_formats_holding_value_profit_and_daily_amount(qtbot):
    stock = StockDraft(
        ts_code="600000.SH",
        stock_name="浦发银行",
        is_holding=True,
        holding=type(
            "Holding",
            (),
            {
                "current_amount": 1200,
                "enable_amount": 1000,
                "market_value": Decimal("1234567.8"),
                "cost_price": Decimal("10.25"),
                "income_balance": Decimal("-2345.67"),
            },
        )(),
        orders=[],
    )
    quote = DailyQuote(
        ts_code="600000.SH",
        trade_date="20260225",
        open=Decimal("10.00"),
        high=Decimal("10.80"),
        low=Decimal("9.80"),
        close=Decimal("10.50"),
        pre_close=Decimal("10.00"),
        change=Decimal("0.50"),
        pct_chg=Decimal("5.00"),
        vol=Decimal("10000"),
        amount=Decimal("250000"),
    )
    card = StockCard(stock, daily_quote=quote)
    qtbot.addWidget(card)

    metrics = [label.text() for label in card.findChildren(QLabel, "stock_metric_chip")]
    profit_metric = next(label for label in card.findChildren(QLabel, "stock_metric_chip") if label.text().startswith("盈亏 "))

    assert [item.split(" ", 1)[0] for item in metrics] == ["市值", "持仓", "成本", "盈亏"]
    assert "市值 1,234,567.80" in metrics
    assert "持仓 1,200" in metrics
    assert "盈亏 -2,345.67" in metrics
    assert profit_metric.property("tone") in {None, ""}
    assert card.findChild(QLabel, "stock_daily_amount").text() == "2.50亿"


def test_stock_card_daily_quote_zero_pct_uses_black_text_and_red_kline(qtbot):
    stock = StockDraft(ts_code="600000.SH", stock_name="浦发银行", is_holding=False, orders=[])
    quote = DailyQuote(
        ts_code="600000.SH",
        trade_date="20260225",
        open=Decimal("10.00"),
        high=Decimal("10.30"),
        low=Decimal("9.80"),
        close=Decimal("10.00"),
        pre_close=Decimal("10.00"),
        change=Decimal("0"),
        pct_chg=Decimal("0"),
        vol=Decimal("10000"),
        amount=Decimal("1000000"),
    )
    card = StockCard(stock, daily_quote=quote)
    qtbot.addWidget(card)

    pct = card.findChild(QLabel, "stock_daily_pct")
    kline = card.findChild(QWidget, "stock_daily_kline")

    assert pct.text() == "0.00%"
    assert pct.property("tone") == "flat"
    assert kline.property("tone") == "up"


def test_stock_card_hides_daily_quote_when_data_missing(qtbot):
    stock = StockDraft(ts_code="600000.SH", stock_name="浦发银行", is_holding=False, orders=[])
    card = StockCard(stock)
    qtbot.addWidget(card)

    assert card.findChild(QWidget, "stock_daily_quote").isHidden() is True


def test_empty_order_sections_collapse_to_embedded_header_height(qtbot):
    stock = StockDraft(
        ts_code="600000.SH",
        stock_name="浦发银行",
        is_holding=False,
        orders=[OrderDraft("buy_stop", Decimal("10.00"), 100)],
    )
    card = StockCard(stock)
    qtbot.addWidget(card)
    card.show()
    qtbot.waitExposed(card)

    filled_group = card.findChild(QGroupBox, "order_group_buy_stop")
    empty_group = card.findChild(QGroupBox, "order_group_sell_loss")
    empty_header = empty_group.findChild(QWidget, "order_group_header")

    assert empty_group.height() <= empty_header.height() + 12
    assert filled_group.height() >= empty_group.height() + 28


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
    assert window.stock_update_button.text() == "生成数据"
    assert window.stock_update_button.isEnabled() is True

    window.set_stock_update_state("updated_disabled")
    assert window.stock_update_button.text() == "数据已更新"
    assert window.stock_update_button.isEnabled() is False

    window.set_stock_update_state("update_enabled")
    assert window.stock_update_button.text() == "更新数据"
    assert window.stock_update_button.isEnabled() is True

    window.set_stock_update_state("update_disabled_non_trade_day")
    assert window.stock_update_button.text() == "更新数据"
    assert window.stock_update_button.isEnabled() is False


def test_main_window_empty_state(qtbot):
    window = MainWindow(auto_update_stock_basic=False)
    qtbot.addWidget(window)

    empty_label = window.stock_layout.itemAt(0).widget()
    available = window.screen().availableGeometry()

    assert "直接添加股票" in empty_label.text()
    assert window.minimumWidth() <= 640
    assert window.minimumHeight() <= 360
    assert window.width() == window.minimumWidth()
    assert window.height() == available.height()
    assert window.geometry().right() == available.right()
    assert window.findChild(type(window.account_bar), "top_tool_panel") is not None


def test_date_combo_shows_weekday(qtbot, sqlite_conn):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)
    window.resize(900, 720)
    window.show()
    qtbot.waitExposed(window)

    assert window.date_combo.itemText(0).startswith("20260225 周三")
    assert window.stock_nav_layout.indexOf(window.date_combo) == 0
    margins = window.stock_nav_layout.contentsMargins()
    assert margins.top() == 5
    assert margins.bottom() == 5
    assert window.stock_nav_bar.height() <= window.stock_nav_bar.sizeHint().height() + 2
    assert abs(window.tabs.geometry().center().x() - window.stock_nav_bar.rect().center().x()) <= 2
    assert abs(window.tabs.geometry().center().y() - window.stock_nav_bar.rect().center().y()) <= 2


def test_stock_jump_combo_lists_visible_stocks_and_jumps_to_card(qtbot, sqlite_conn, monkeypatch):
    draft = make_fixture_draft(sqlite_conn)
    window = MainWindow(draft)
    qtbot.addWidget(window)
    captured = []
    monkeypatch.setattr(window.stock_scroll, "ensureWidgetVisible", lambda widget: captured.append(widget.stock.ts_code))

    assert [window.stock_jump_combo.itemText(index) for index in range(window.stock_jump_combo.count())] == [
        "002153.SZ 石基信息",
        "300162.SZ 雷曼光电",
        "300251.SZ 光线传媒",
    ]

    window.stock_jump_combo.activated.emit(1)

    assert captured == ["300162.SZ"]


def test_auto_update_runs_when_stock_data_missing(qtbot, monkeypatch):
    started = []

    class FakeWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
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

        def stock_update_fetch_plan(self, **kwargs):
            return {
                "token": "token",
                "today": "20260609",
                "calendar_start_date": "20260101",
                "calendar_end_date": "20271231",
            }

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.StockUpdateWorker", FakeWorker)

    window = MainWindow(service=FakeService(), auto_update_stock_basic=True)
    qtbot.addWidget(window)

    assert started == []
    qtbot.waitUntil(lambda: started == [True])
    assert started == [True]


def test_auto_update_keeps_stock_worker_alive_until_finished(qtbot, monkeypatch):
    workers = []

    class FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class RunningWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
            self.failedWithMessage = FakeSignal()
            self.finished = FakeSignal()
            workers.append(self)

        def isRunning(self):
            return True

        def start(self):
            return None

        def requestInterruption(self):
            return None

        def quit(self):
            return None

        def wait(self, _ms):
            return True

    class FakeService:
        class FakeStockMatcher:
            def sync_from_tushare(self):
                return None

        stock_matcher = FakeStockMatcher()

        def stock_update_button_state(self, today):
            return "generate"

        def list_manage_dates(self):
            return []

        def stock_update_fetch_plan(self, **kwargs):
            return {
                "token": "token",
                "today": "20260609",
                "calendar_start_date": "20260101",
                "calendar_end_date": "20271231",
            }

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.StockUpdateWorker", RunningWorker)

    window = MainWindow(service=FakeService(), auto_update_stock_basic=True)
    qtbot.addWidget(window)

    assert workers == []
    qtbot.waitUntil(lambda: workers == [window._stock_update_worker])
    assert workers == [window._stock_update_worker]
    assert workers[0] in window._background_workers


def test_manual_stock_update_uses_background_worker(qtbot, monkeypatch):
    started = []
    sync_calls = []

    class FakeSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class RunningWorker:
        def __init__(self, *args, **kwargs):
            self.finishedWithRows = FakeSignal()
            self.failedWithMessage = FakeSignal()
            self.finished = FakeSignal()
            started.append(args)

        def isRunning(self):
            return True

        def start(self):
            return None

        def requestInterruption(self):
            return None

        def quit(self):
            return None

        def wait(self, _ms):
            return True

    class FakeService:
        class FakeStockMatcher:
            def sync_from_tushare(self):
                return None

        stock_matcher = FakeStockMatcher()

        def stock_update_button_state(self, today):
            return "update_enabled"

        def list_manage_dates(self):
            return []

        def stock_update_fetch_plan(self, **kwargs):
            return {
                "token": "token",
                "today": "20260609",
                "calendar_start_date": "20260101",
                "calendar_end_date": "20271231",
            }

        def update_stock_basic(self, **kwargs):
            sync_calls.append(kwargs)
            return 1

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.StockUpdateWorker", RunningWorker)

    window = MainWindow(service=FakeService(), auto_update_stock_basic=False)
    qtbot.addWidget(window)
    window._handle_stock_update()

    assert len(started) == 1
    assert sync_calls == []
    assert window.stock_update_button.text() == "更新中..."
    assert window.stock_update_button.isEnabled() is False
    assert window._stock_update_worker in window._background_workers


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
    metrics = [label.text() for label in window.findChildren(type(window.total_label), "stock_metric_chip")]
    statuses = [label.toolTip() for label in window.findChildren(QLabel, "order_status_indicator")]
    pending_badges = [label.text() for label in window.findChildren(type(window.total_label), "pending_order_badge")]

    assert any("止盈合计 1,400，不等于持仓 2,800" in item for item in warnings)
    assert not any(item.startswith("可卖 ") for item in metrics)
    assert "已确认" in statuses
    assert pending_badges == []
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)
    assert row.amount_label.text() == "金额 17,710.00"
    assert not row.amount_label.isHidden()

    row.shares_input.set_value(1500)

    assert row.amount_label.text() == "金额 18,975.00"


def test_buy_orders_show_amount_and_cash_summary(qtbot, sqlite_conn):
    initialize_schema(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_stop", Decimal("9.80"), 1000)
    window = MainWindow(store.load_draft("20260225"))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    assert window.opening_amount_label.text() == "开仓金额 9,800.00"
    assert not window.opening_amount_label.isHidden()
    assert row.amount_label.text() == "金额 9,800.00"
    assert not row.amount_label.isHidden()
    assert row.confirm_button.width() <= 44
    assert row.delete_button.width() <= 44
    assert row.type_combo.isHidden()
    assert row.price_label.text() == "价格 >="
    assert row.status_indicator.width() == 10
    group = row.parent()
    while group is not None and not isinstance(group, QGroupBox):
        group = group.parent()
    assert group is not None
    header = group.findChild(QWidget, "order_group_header")
    title_wrap = header.findChild(QWidget, "order_group_title_wrap")
    assert row.status_indicator.mapToGlobal(QPoint(0, 0)).x() < row.price_label.mapToGlobal(QPoint(0, 0)).x()
    assert 8 <= title_wrap.geometry().left() <= 14

    row.shares_input.set_value(2000)

    assert row.amount_label.text() == "金额 19,600.00"


def test_order_row_uses_context_menu_for_digit_width(qtbot, sqlite_conn):
    initialize_schema(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    store = DraftStore(sqlite_conn)
    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path="/tmp/order_data/20260225.json",
    )
    order_id = store.add_order(draft.manage_date, "300162.SZ", "雷曼光电", "buy_stop", Decimal("9.80"), 1000)
    window = MainWindow(store.load_draft("20260225"))
    qtbot.addWidget(window)
    row = next(row for row in window.findChildren(OrderRow) if row.order.id == order_id)

    assert row.findChildren(type(row.confirm_button), "digit_width_button") == []
    width_before = row.price_input.width()
    assert row.price_input.can_remove_high_digit() is False
    row.price_input.add_high_digit()

    assert row.price_input.width() > width_before
    assert row.price_input.can_remove_high_digit() is True
