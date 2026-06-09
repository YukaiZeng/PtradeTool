from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ptrade_order_tool.models import OrderDraft, StockDraft
from ptrade_order_tool.ui.order_row import ORDER_LABELS, OrderRow


GROUP_META = {
    "buy_stop": ("buy", "突破买入"),
    "buy_limit": ("buy", "回调买入"),
    "sell_profit": ("sell_profit", "止盈卖出"),
    "sell_loss": ("sell_loss", "止损卖出"),
}


class StockCard(QFrame):
    confirmRequested = Signal(object)
    deleteRequested = Signal(object)
    addOrderRequested = Signal(object, str)

    def __init__(self, stock: StockDraft, parent=None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.stock = stock
        self.read_only = read_only
        self.setObjectName(f"stock_card_{stock.ts_code}")
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

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
            header_layout.addWidget(pending_badge)

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

        orders_grid = QGridLayout()
        orders_grid.setContentsMargins(0, 0, 0, 0)
        orders_grid.setHorizontalSpacing(10)
        orders_grid.setVerticalSpacing(10)
        layout.addLayout(orders_grid)

        order_positions = {
            "buy_stop": (0, 0),
            "sell_profit": (0, 1),
            "buy_limit": (1, 0),
            "sell_loss": (1, 1),
        }
        for order_type, label in ORDER_LABELS.items():
            _, compact_label = GROUP_META[order_type]
            group_box = QGroupBox(f"{compact_label}  {len(grouped.get(order_type, []))}")
            group_box.setObjectName(f"order_group_{order_type}")
            group_box.setProperty("side", GROUP_META[order_type][0])
            group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(8, 10, 8, 8)
            group_layout.setSpacing(6)
            orders = grouped.get(order_type, [])
            if not orders:
                empty_order_label = QLabel("暂无订单")
                empty_order_label.setObjectName("empty_order_label")
                group_layout.addWidget(empty_order_label)
            for order in orders:
                row = OrderRow(order, read_only=read_only)
                row.confirmRequested.connect(self.confirmRequested)
                row.deleteRequested.connect(self.deleteRequested)
                group_layout.addWidget(row)
            add_button = QPushButton(f"新增{compact_label}")
            add_button.setObjectName(f"add_order_{order_type}_{stock.ts_code}")
            add_button.setEnabled(not read_only)
            add_button.clicked.connect(lambda checked=False, value=order_type: self.addOrderRequested.emit(self.stock, value))
            add_row = QWidget()
            add_layout = QHBoxLayout(add_row)
            add_layout.setContentsMargins(0, 0, 0, 0)
            add_layout.addStretch(1)
            add_layout.addWidget(add_button)
            group_layout.addWidget(add_row)
            row, column = order_positions[order_type]
            orders_grid.addWidget(group_box, row, column)
        orders_grid.setColumnStretch(0, 1)
        orders_grid.setColumnStretch(1, 1)

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
