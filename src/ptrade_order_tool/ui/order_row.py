from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ptrade_order_tool.models import OrderDraft, OrderType
from ptrade_order_tool.ui.digit_input import DigitInput


ORDER_LABELS: dict[OrderType, str] = {
    "buy_stop": "突破买",
    "buy_limit": "回调买",
    "sell_profit": "止盈",
    "sell_loss": "止损",
}

ORDER_CONDITIONS: dict[OrderType, str] = {
    "buy_stop": ">=",
    "buy_limit": "<=",
    "sell_profit": ">=",
    "sell_loss": "<=",
}

ORDER_SIDES: dict[OrderType, str] = {
    "buy_stop": "buy",
    "buy_limit": "buy",
    "sell_profit": "sell_profit",
    "sell_loss": "sell_loss",
}


class OrderRow(QWidget):
    confirmRequested = Signal(object)
    deleteRequested = Signal(object)
    changed = Signal(object)
    typeChanged = Signal(object)

    def __init__(self, order: OrderDraft, parent: QWidget | None = None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.order = order
        self.read_only = read_only
        self.setObjectName("order_row")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(4)

        self.type_combo = QComboBox()
        self.type_combo.setObjectName("order_type_combo")
        for order_type, label in ORDER_LABELS.items():
            self.type_combo.addItem(label, order_type)
        self.type_combo.setCurrentIndex(list(ORDER_LABELS).index(order.order_type))
        self.type_combo.setFixedWidth(132)

        self.price_input = DigitInput("price")
        self.price_input.setObjectName("order_price_input")
        self.price_input.set_value(order.price)

        self.shares_input = DigitInput("shares")
        self.shares_input.setObjectName("order_shares_input")
        self.shares_input.set_value(order.shares)

        self.status_indicator = QLabel("")
        self.status_indicator.setObjectName("order_status_indicator")
        self.status_indicator.setFixedSize(10, 18)
        self.amount_label = QLabel("")
        self.amount_label.setObjectName("order_amount_label")

        self.confirm_button = QPushButton("确认")
        self.confirm_button.setObjectName("order_confirm_button")
        self.confirm_button.setFixedWidth(44)
        self.confirm_button.clicked.connect(lambda: self.confirmRequested.emit(self))

        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("order_delete_button")
        self.delete_button.setFixedWidth(44)
        self.delete_button.clicked.connect(lambda: self.deleteRequested.emit(self))

        self.type_combo.hide()

        value_row = QWidget()
        self.value_layout = QHBoxLayout(value_row)
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        self.value_layout.setSpacing(4)
        self.price_label = QLabel(f"价格 {ORDER_CONDITIONS[order.order_type]}")
        self.price_label.setObjectName("order_field_label")
        self.value_layout.addWidget(self.status_indicator)
        self.value_layout.addWidget(self.price_label)
        self.value_layout.addWidget(self.price_input)
        self.shares_label = QLabel("股数")
        self.shares_label.setObjectName("order_field_label")
        self.value_layout.addWidget(self.shares_label)
        self.value_layout.addWidget(self.shares_input)
        self.value_layout.addWidget(self.amount_label)
        self.value_layout.addStretch(1)
        self.value_layout.addWidget(self.confirm_button)
        self.value_layout.addWidget(self.delete_button)
        layout.addWidget(value_row)

        self._apply_color()
        self._refresh_amount()
        self._apply_status_style()
        self.type_combo.currentIndexChanged.connect(self._handle_type_changed)
        self.price_input.valueChanged.connect(self._handle_value_changed)
        self.shares_input.valueChanged.connect(self._handle_value_changed)
        self.set_read_only(read_only)

    def selected_order_type(self) -> OrderType:
        return self.type_combo.currentData()

    def selected_price(self) -> Decimal:
        return self.price_input.value()

    def selected_shares(self) -> int:
        return self.shares_input.value()

    def _apply_color(self) -> None:
        order_type = self.selected_order_type()
        side = ORDER_SIDES[order_type]
        self.setProperty("side", side)
        self.type_combo.setProperty("side", side)
        self.price_label.setText(f"价格 {ORDER_CONDITIONS[order_type]}")
        self._refresh_dynamic_style(self)
        self._refresh_dynamic_style(self.type_combo)

    def _handle_type_changed(self) -> None:
        old_order_type = self.order.order_type
        self._apply_color()
        self._refresh_amount()
        self._mark_changed(emit_signal=False)
        if self.selected_order_type() != old_order_type:
            self.typeChanged.emit(self)

    def _handle_value_changed(self) -> None:
        self._refresh_amount()
        self._mark_changed()

    def _refresh_amount(self) -> None:
        amount = self.selected_price() * Decimal(self.selected_shares())
        self.amount_label.setText(f"金额 {amount:,.2f}")
        self.amount_label.show()

    def set_read_only(self, read_only: bool) -> None:
        self.read_only = read_only
        self.type_combo.setEnabled(not read_only)
        self.price_label.setEnabled(not read_only)
        self.price_input.setEnabled(not read_only)
        self.shares_label.setEnabled(not read_only)
        self.shares_input.setEnabled(not read_only)
        self.confirm_button.setEnabled(not read_only)
        self.delete_button.setEnabled(not read_only)

    def mark_unconfirmed(self) -> None:
        self.order.confirmed = False
        self.confirm_button.setText("确认")
        self._apply_status_style()

    def _mark_changed(self, *, emit_signal: bool = True) -> None:
        if self.read_only:
            return
        if (
            self.selected_order_type() == self.order.order_type
            and self.selected_price() == self.order.price
            and self.selected_shares() == self.order.shares
        ):
            return
        self.order.order_type = self.selected_order_type()
        self.order.price = self.selected_price()
        self.order.shares = self.selected_shares()
        self.mark_unconfirmed()
        if emit_signal:
            self.changed.emit(self)

    def _status_text(self) -> str:
        if self.order.confirmed:
            return "已确认"
        if self.order.source == "inherited":
            return "继承待确认"
        return "未确认"

    def _apply_status_style(self) -> None:
        if self.order.confirmed:
            status = "confirmed"
        elif self.order.source == "inherited":
            status = "inherited"
        else:
            status = "pending"
        self.status_indicator.setProperty("status", status)
        self.status_indicator.setToolTip(self._status_text())
        self.confirm_button.setProperty("status", status)
        self._refresh_dynamic_style(self.status_indicator)
        self._refresh_dynamic_style(self.confirm_button)

    def _refresh_dynamic_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
