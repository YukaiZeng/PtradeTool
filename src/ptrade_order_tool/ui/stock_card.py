from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ptrade_order_tool.models import OrderDraft, StockDraft
from ptrade_order_tool.ui.order_row import ORDER_LABELS, OrderRow


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
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel(f"{stock.ts_code}  {stock.stock_name}")
        self.header.setObjectName("stock_card_header")
        self.header.setStyleSheet("font-weight: 700; font-size: 15px;")
        layout.addWidget(self.header)

        if stock.holding:
            holding = stock.holding
            self.holding_label = QLabel(
                f"可卖 {holding.enable_amount} | 市值 {holding.market_value} | 成本 {holding.cost_price} | 盈亏 {holding.income_balance}"
            )
            self.holding_label.setObjectName("stock_card_holding")
            layout.addWidget(self.holding_label)

        grouped: dict[str, list[OrderDraft]] = defaultdict(list)
        for order in stock.orders:
            grouped[order.order_type].append(order)

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

        for order_type, label in ORDER_LABELS.items():
            group_box = QGroupBox(label)
            group_box.setObjectName(f"order_group_{order_type}")
            group_layout = QVBoxLayout(group_box)
            for order in grouped.get(order_type, []):
                row = OrderRow(order, read_only=read_only)
                row.confirmRequested.connect(self.confirmRequested)
                row.deleteRequested.connect(self.deleteRequested)
                group_layout.addWidget(row)
            add_button = QPushButton(f"新增{label}")
            add_button.setObjectName(f"add_order_{order_type}_{stock.ts_code}")
            add_button.setEnabled(not read_only)
            add_button.clicked.connect(lambda checked=False, value=order_type: self.addOrderRequested.emit(self.stock, value))
            add_row = QWidget()
            add_layout = QHBoxLayout(add_row)
            add_layout.setContentsMargins(0, 0, 0, 0)
            add_layout.addStretch(1)
            add_layout.addWidget(add_button)
            group_layout.addWidget(add_row)
            layout.addWidget(group_box)

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
