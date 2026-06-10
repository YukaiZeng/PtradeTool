from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ptrade_order_tool.models import OrderDraft, OrderType
from ptrade_order_tool.ui.digit_input import DigitInput


ORDER_LABELS: dict[OrderType, str] = {
    "buy_stop": "突破买 >=",
    "buy_limit": "回调买 <=",
    "sell_profit": "止盈 >=",
    "sell_loss": "止损 <=",
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
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

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

        self.status_label = QLabel(self._status_text())
        self.status_label.setObjectName("order_status_label")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumWidth(84)
        self.status_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.amount_label = QLabel("")
        self.amount_label.setObjectName("order_amount_label")

        self.confirm_button = QPushButton("确认" if not order.confirmed else "已确认")
        self.confirm_button.setObjectName("order_confirm_button")
        self.confirm_button.setFixedWidth(70)
        self.confirm_button.clicked.connect(lambda: self.confirmRequested.emit(self))

        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("order_delete_button")
        self.delete_button.setFixedWidth(64)
        self.delete_button.clicked.connect(lambda: self.deleteRequested.emit(self))

        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)
        top_layout.addWidget(self.type_combo)
        top_layout.addStretch(1)
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.confirm_button)
        top_layout.addWidget(self.delete_button)
        layout.addWidget(top_row)

        value_row = QWidget()
        value_layout = QHBoxLayout(value_row)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(6)
        self.price_label = QLabel("价格")
        self.price_label.setObjectName("order_field_label")
        value_layout.addWidget(self.price_label)
        value_layout.addWidget(self.price_input)
        self.shares_label = QLabel("股数")
        self.shares_label.setObjectName("order_field_label")
        value_layout.addWidget(self.shares_label)
        value_layout.addWidget(self.shares_input)
        value_layout.addWidget(self.amount_label)
        value_layout.addStretch(1)
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
        if self.selected_order_type() not in {"buy_stop", "buy_limit"}:
            self.amount_label.hide()
            return
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
        self.status_label.setText(self._status_text())
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
        self.status_label.setProperty("status", status)
        self.confirm_button.setProperty("status", status)
        self._refresh_dynamic_style(self.status_label)
        self._refresh_dynamic_style(self.confirm_button)

    def _refresh_dynamic_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
