from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ptrade_order_tool.models import DailyQuote, OrderDraft, StockDraft
from ptrade_order_tool.ui.order_row import ORDER_LABELS, OrderRow


GROUP_META = {
    "buy_stop": ("buy", "突破买"),
    "buy_limit": ("buy", "回调买"),
    "sell_profit": ("sell_profit", "止盈"),
    "sell_loss": ("sell_loss", "止损"),
}


class EmbeddedOrderGroup(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self._embedded_header: QWidget | None = None
        self._collapsed = False

    def set_embedded_header(self, header: QWidget) -> None:
        self._embedded_header = header
        header.setParent(self)
        header.show()
        header.raise_()
        self._position_embedded_header()

    def set_collapsed_to_header(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        if self._collapsed and self._embedded_header is not None:
            return QSize(hint.width(), self._embedded_header.height() + 8)
        return hint

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        if self._collapsed and self._embedded_header is not None:
            return QSize(hint.width(), self._embedded_header.height() + 8)
        return hint

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._position_embedded_header()

    def _position_embedded_header(self) -> None:
        if self._embedded_header is None:
            return
        self._embedded_header.setGeometry(9, 0, max(0, self.width() - 18), 22)
        self._embedded_header.raise_()


class MiniKLine(QWidget):
    def __init__(self, quote: DailyQuote | None = None, parent=None) -> None:
        super().__init__(parent)
        self.quote = quote
        self.setObjectName("stock_daily_kline")
        self.setFixedSize(22, 18)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setProperty("tone", self._tone())

    def set_quote(self, quote: DailyQuote | None) -> None:
        self.quote = quote
        self.setProperty("tone", self._tone())
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self.quote is None:
            return
        high = self.quote.high
        low = self.quote.low
        if high < low:
            high, low = low, high
        span = high - low
        if span <= 0:
            span = Decimal("1")
        top = 2
        bottom = self.height() - 3

        def y_for(value: Decimal) -> int:
            ratio = (high - value) / span
            return int(top + float(ratio) * (bottom - top))

        open_y = y_for(self.quote.open)
        close_y = y_for(self.quote.close)
        high_y = y_for(high)
        low_y = y_for(low)
        color = QColor("#d40000" if self._tone() == "up" else "#008f39")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 1))
        center_x = self.width() // 2
        painter.drawLine(center_x, high_y, center_x, low_y)
        body_top = min(open_y, close_y)
        body_height = max(3, abs(close_y - open_y))
        painter.fillRect(center_x - 4, body_top, 8, body_height, color)

    def _tone(self) -> str:
        if self.quote is None:
            return "up"
        if self.quote.pct_chg == 0:
            return "up"
        return "up" if self.quote.close >= self.quote.open else "down"


class StockCard(QFrame):
    confirmRequested = Signal(object)
    deleteRequested = Signal(object)
    orderChanged = Signal(object)
    orderTypeChanged = Signal(object)
    addOrderRequested = Signal(object, str)
    deleteStockRequested = Signal(object)

    def __init__(
        self,
        stock: StockDraft,
        parent=None,
        *,
        read_only: bool = False,
        daily_quote: DailyQuote | None = None,
    ) -> None:
        super().__init__(parent)
        self.stock = stock
        self.read_only = read_only
        self.setObjectName(f"stock_card_{stock.ts_code}")
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self.header = QLabel(f"{stock.ts_code}  {stock.stock_name}")
        self.header.setObjectName("stock_card_header")
        self.type_badge = QLabel("持仓" if stock.is_holding else "开仓")
        self.type_badge.setObjectName("stock_type_badge")
        self.type_badge.setProperty("kind", "holding" if stock.is_holding else "opening")
        header_layout.addWidget(self.header)
        header_layout.addWidget(self.type_badge)
        self.daily_quote_widget = self._make_daily_quote_widget(daily_quote)
        header_layout.addWidget(self.daily_quote_widget)
        header_layout.addStretch(1)
        layout.addWidget(header_row)

        if stock.holding:
            holding = stock.holding
            metrics_row = QWidget()
            metrics_layout = QHBoxLayout(metrics_row)
            metrics_layout.setContentsMargins(0, 0, 0, 0)
            metrics_layout.setSpacing(6)
            for label, value, tone in (
                ("持仓", holding.current_amount, ""),
                ("可卖", holding.enable_amount, ""),
                ("市值", holding.market_value, ""),
                ("成本", holding.cost_price, ""),
                ("盈亏", holding.income_balance, "negative" if holding.income_balance < 0 else "positive"),
            ):
                metric = QLabel(f"{label} {value}")
                metric.setObjectName("stock_metric_chip")
                if tone:
                    metric.setProperty("tone", tone)
                metrics_layout.addWidget(metric)
            metrics_layout.addStretch(1)
            layout.addWidget(metrics_row)

        grouped: dict[str, list[OrderDraft]] = defaultdict(list)
        for order in stock.orders:
            grouped[order.order_type].append(order)

        unconfirmed_count = sum(1 for order in stock.orders if not order.confirmed)
        if unconfirmed_count:
            pending_badge = QLabel(f"{unconfirmed_count} 个待确认")
            pending_badge.setObjectName("pending_order_badge")
            pending_badge.setAlignment(Qt.AlignCenter)
            pending_badge.setMinimumWidth(84)
            header_layout.addWidget(pending_badge)
        self.delete_stock_button = QPushButton("删除")
        self.delete_stock_button.setObjectName(f"delete_stock_{stock.ts_code}")
        self.delete_stock_button.setProperty("role", "delete_stock")
        self.delete_stock_button.setEnabled(not read_only)
        self.delete_stock_button.setFixedWidth(44)
        self.delete_stock_button.clicked.connect(lambda: self.deleteStockRequested.emit(self.stock))
        header_layout.addWidget(self.delete_stock_button)

        warning_texts = self._warning_texts(grouped)
        if warning_texts:
            warning_box = QWidget()
            warning_box.setObjectName("stock_card_warning_box")
            warning_layout = QVBoxLayout(warning_box)
            warning_layout.setContentsMargins(8, 6, 8, 6)
            warning_layout.setSpacing(2)
            for text in warning_texts:
                warning_label = QLabel(text)
                warning_label.setObjectName("stock_card_warning")
                warning_layout.addWidget(warning_label)
            layout.addWidget(warning_box)

        self.orders_grid = QGridLayout()
        self.orders_grid.setContentsMargins(0, 0, 0, 0)
        self.orders_grid.setHorizontalSpacing(6)
        self.orders_grid.setVerticalSpacing(4)
        layout.addLayout(self.orders_grid)

        order_positions = {
            "buy_stop": (0, 0),
            "buy_limit": (1, 0),
            "sell_profit": (2, 0),
            "sell_loss": (3, 0),
        }
        for order_type in ORDER_LABELS:
            _, compact_label = GROUP_META[order_type]
            group_box = EmbeddedOrderGroup()
            group_box.setObjectName(f"order_group_{order_type}")
            group_box.setProperty("side", GROUP_META[order_type][0])
            group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(6, 18, 6, 4)
            group_layout.setSpacing(3)
            orders = grouped.get(order_type, [])
            group_header = QWidget()
            group_header.setObjectName("order_group_header")
            group_header.setProperty("side", GROUP_META[order_type][0])
            group_header.setFixedHeight(22)
            group_header_layout = QHBoxLayout(group_header)
            group_header_layout.setContentsMargins(10, 0, 0, 0)
            group_header_layout.setSpacing(6)
            title_wrap = QWidget()
            title_wrap.setObjectName("order_group_title_wrap")
            title_wrap_layout = QHBoxLayout(title_wrap)
            title_wrap_layout.setContentsMargins(0, 0, 0, 0)
            title_wrap_layout.setSpacing(4)
            title_label = QLabel(f"{compact_label}  {len(orders)}")
            title_label.setObjectName(f"order_group_title_{order_type}")
            title_label.setProperty("side", GROUP_META[order_type][0])
            add_button = QPushButton("+")
            add_button.setObjectName(f"add_order_{order_type}_{stock.ts_code}")
            add_button.setProperty("role", "add_order")
            add_button.setEnabled(not read_only)
            add_button.setToolTip(f"新增{compact_label}订单")
            add_button.setFixedSize(18, 18)
            add_button.clicked.connect(lambda checked=False, value=order_type: self.addOrderRequested.emit(self.stock, value))
            title_wrap_layout.addWidget(title_label)
            title_wrap_layout.addWidget(add_button)
            group_header_layout.addWidget(title_wrap)
            group_header_layout.addStretch(1)
            group_box.set_embedded_header(group_header)
            group_box.set_collapsed_to_header(not orders)
            for order in orders:
                row = OrderRow(order, read_only=read_only)
                row.confirmRequested.connect(self.confirmRequested)
                row.deleteRequested.connect(self.deleteRequested)
                row.changed.connect(self.orderChanged)
                row.typeChanged.connect(self.orderTypeChanged)
                group_layout.addWidget(row)
            row, column = order_positions[order_type]
            self.orders_grid.addWidget(group_box, row, column)
        self.orders_grid.setColumnStretch(0, 1)

    def set_daily_quote(self, quote: DailyQuote | None) -> None:
        self._set_daily_quote(quote)

    def _make_daily_quote_widget(self, quote: DailyQuote | None) -> QWidget:
        widget = QWidget()
        widget.setObjectName("stock_daily_quote")
        widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.daily_price_label = QLabel("")
        self.daily_price_label.setObjectName("stock_daily_price")
        self.daily_pct_label = QLabel("")
        self.daily_pct_label.setObjectName("stock_daily_pct")
        self.daily_amount_label = QLabel("")
        self.daily_amount_label.setObjectName("stock_daily_amount")
        self.daily_kline = MiniKLine(quote)
        layout.addWidget(self.daily_price_label)
        layout.addWidget(self.daily_pct_label)
        layout.addWidget(self.daily_amount_label)
        layout.addWidget(self.daily_kline)
        self.daily_quote_widget = widget
        self._set_daily_quote(quote)
        return widget

    def _set_daily_quote(self, quote: DailyQuote | None) -> None:
        self.daily_quote_widget.setVisible(quote is not None)
        if quote is None:
            return
        self.daily_price_label.setText(f"{quote.close:.2f}")
        self.daily_pct_label.setText(_format_pct(quote.pct_chg))
        self.daily_pct_label.setProperty("tone", _pct_tone(quote.pct_chg))
        self.daily_amount_label.setText(_format_amount_yi(quote.amount))
        self.daily_kline.set_quote(quote)
        self._refresh_dynamic_style(self.daily_pct_label)
        self._refresh_dynamic_style(self.daily_kline)

    def _warning_texts(self, grouped: dict[str, list[OrderDraft]]) -> list[str]:
        if not self.stock.holding:
            return []
        enable_amount = self.stock.holding.enable_amount
        profit_total = sum(order.shares for order in grouped.get("sell_profit", []))
        loss_total = sum(order.shares for order in grouped.get("sell_loss", []))
        warnings = []
        if profit_total and profit_total != enable_amount:
            warnings.append(f"止盈合计 {profit_total}，不等于可卖 {enable_amount}")
        if loss_total and loss_total != enable_amount:
            warnings.append(f"止损合计 {loss_total}，不等于可卖 {enable_amount}")
        return warnings

    def _refresh_dynamic_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _pct_tone(pct_chg: Decimal) -> str:
    if pct_chg > 0:
        return "up"
    if pct_chg < 0:
        return "down"
    return "flat"


def _format_pct(pct_chg: Decimal) -> str:
    prefix = "+" if pct_chg > 0 else ""
    return f"{prefix}{pct_chg:.2f}%"


def _format_amount_yi(amount: Decimal) -> str:
    yi = amount / Decimal("100000")
    return f"{yi:.1f}亿"
