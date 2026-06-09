from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from ptrade_order_tool.models import OrderDraft, OrderType
from ptrade_order_tool.ui.digit_input import DigitInput


ORDER_LABELS: dict[OrderType, str] = {
    "buy_stop": "突破买入 >=",
    "buy_limit": "回调买入 <=",
    "sell_profit": "止盈 >=",
    "sell_loss": "止损 <=",
}

ORDER_COLORS: dict[OrderType, str] = {
    "buy_stop": "#2563eb",
    "buy_limit": "#0891b2",
    "sell_profit": "#dc2626",
    "sell_loss": "#ea580c",
}


class OrderRow(QWidget):
    confirmRequested = Signal(object)
    deleteRequested = Signal(object)

    def __init__(self, order: OrderDraft, parent: QWidget | None = None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.order = order
        self.read_only = read_only
        self.setObjectName("order_row")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.type_combo = QComboBox()
        self.type_combo.setObjectName("order_type_combo")
        for order_type, label in ORDER_LABELS.items():
            self.type_combo.addItem(label, order_type)
        self.type_combo.setCurrentIndex(list(ORDER_LABELS).index(order.order_type))

        self.price_input = DigitInput("price")
        self.price_input.setObjectName("order_price_input")
        self.price_input.set_value(order.price)

        self.shares_input = DigitInput("shares")
        self.shares_input.setObjectName("order_shares_input")
        self.shares_input.set_value(order.shares)

        self.status_label = QLabel(self._status_text())
        self.status_label.setObjectName("order_status_label")

        self.confirm_button = QPushButton("确认" if not order.confirmed else "已确认")
        self.confirm_button.setObjectName("order_confirm_button")
        self.confirm_button.clicked.connect(lambda: self.confirmRequested.emit(self))

        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("order_delete_button")
        self.delete_button.clicked.connect(lambda: self.deleteRequested.emit(self))

        layout.addWidget(self.type_combo)
        self.price_label = QLabel("价格")
        self.price_label.setObjectName("order_field_label")
        layout.addWidget(self.price_label)
        layout.addWidget(self.price_input)
        self.shares_label = QLabel("股数")
        self.shares_label.setObjectName("order_field_label")
        layout.addWidget(self.shares_label)
        layout.addWidget(self.shares_input)
        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.confirm_button)
        layout.addWidget(self.delete_button)

        self._apply_color()
        self.type_combo.currentIndexChanged.connect(self._apply_color)
        self.set_read_only(read_only)

    def selected_order_type(self) -> OrderType:
        return self.type_combo.currentData()

    def selected_price(self) -> Decimal:
        return self.price_input.value()

    def selected_shares(self) -> int:
        return self.shares_input.value()

    def _apply_color(self) -> None:
        order_type = self.selected_order_type()
        color = ORDER_COLORS[order_type]
        self.setStyleSheet(
            f"""
            QWidget#order_row {{
                border-left: 4px solid {color};
                background: #ffffff;
            }}
            QComboBox {{
                color: {color};
                font-weight: 600;
            }}
            QLabel#order_status_label {{
                color: {color};
                font-weight: 600;
                min-width: 72px;
            }}
            QLabel#order_field_label {{
                color: #5b6470;
                font-weight: 600;
            }}
            """
        )

    def set_read_only(self, read_only: bool) -> None:
        self.read_only = read_only
        self.type_combo.setEnabled(not read_only)
        self.price_label.setEnabled(not read_only)
        self.price_input.setEnabled(not read_only)
        self.shares_label.setEnabled(not read_only)
        self.shares_input.setEnabled(not read_only)
        self.confirm_button.setEnabled(not read_only)
        self.delete_button.setEnabled(not read_only)

    def _status_text(self) -> str:
        if self.order.confirmed:
            return "已确认"
        if self.order.source == "inherited":
            return "继承待确认"
        return "未确认"
