from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget


class DigitButton(QPushButton):
    digitChanged = Signal(int, str)

    def __init__(self, index: int, digit: str, parent: QWidget | None = None) -> None:
        super().__init__(digit, parent)
        self.index = index
        self.setObjectName("digit_button")
        self.setFixedSize(26, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def set_digit(self, digit: str) -> None:
        self.setText(digit)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            menu = QMenu(self)
            for digit in "0123456789":
                action = QAction(digit, menu)
                action.triggered.connect(lambda checked=False, value=digit: self.digitChanged.emit(self.index, value))
                menu.addAction(action)
            menu.exec(self.mapToGlobal(event.pos()))
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        current = int(self.text())
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.digitChanged.emit(self.index, str((current + delta) % 10))
        event.accept()


class DigitInput(QWidget):
    valueChanged = Signal()

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if kind not in {"price", "shares"}:
            raise ValueError("kind must be 'price' or 'shares'")
        self.kind = kind
        self.default_integer_digits = 4
        self.fraction_digits = 2 if kind == "price" else 0
        self._integer_digits = ["0"] * self.default_integer_digits
        self._fraction_digits = ["0"] * self.fraction_digits
        self._cursor = 0
        self._buttons: list[DigitButton] = []

        self.setFocusPolicy(Qt.StrongFocus)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._rebuild()

    def text(self) -> str:
        integer = "".join(self._integer_digits)
        if self.kind == "price":
            return f"{integer}.{''.join(self._fraction_digits)}"
        return integer

    def value(self) -> Decimal | int:
        if self.kind == "price":
            return Decimal(self.text())
        return int(self.text())

    def set_value(self, value: Decimal | int | float | str) -> None:
        if self.kind == "price":
            text = f"{Decimal(str(value)):.2f}"
            integer, fraction = text.split(".")
            self._ensure_integer_width(len(integer))
            self._integer_digits = list(integer.zfill(len(self._integer_digits)))
            self._fraction_digits = list(fraction)
        else:
            integer = str(int(value))
            self._ensure_integer_width(len(integer))
            self._integer_digits = list(integer.zfill(len(self._integer_digits)))
        self._cursor = 0
        self._refresh()
        self._update_fixed_width()
        self.valueChanged.emit()

    def add_high_digit(self) -> None:
        self._integer_digits.insert(0, "0")
        self._cursor = 0
        self._rebuild()
        self._update_fixed_width()
        self.valueChanged.emit()

    def remove_high_digit(self) -> None:
        if len(self._integer_digits) <= self.default_integer_digits:
            return
        self._integer_digits.pop(0)
        self._cursor = 0
        self._rebuild()
        self._update_fixed_width()
        self.valueChanged.emit()

    def set_digit(self, index: int, digit: str) -> None:
        if digit not in "0123456789":
            raise ValueError("digit must be 0-9")
        editable = self._editable_digits()
        if index < 0 or index >= len(editable):
            raise IndexError(index)
        section, local_index = editable[index]
        if section == "integer":
            self._integer_digits[local_index] = digit
        else:
            self._fraction_digits[local_index] = digit
        self._refresh()
        self.valueChanged.emit()

    def is_valid(self) -> bool:
        value = self.value()
        if self.kind == "price":
            return isinstance(value, Decimal) and value > 0
        return isinstance(value, int) and value > 0 and value % 100 == 0

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        text = event.text()
        if text and text in "0123456789":
            self.set_digit(self._cursor, text)
            self._cursor = min(self._cursor + 1, len(self._editable_digits()) - 1)
            event.accept()
            return
        if event.key() == Qt.Key_Backspace:
            self._cursor = max(0, self._cursor - 1)
            self.set_digit(self._cursor, "0")
            event.accept()
            return
        super().keyPressEvent(event)

    def _ensure_integer_width(self, width: int) -> None:
        while len(self._integer_digits) < max(width, self.default_integer_digits):
            self._integer_digits.insert(0, "0")

    def _editable_digits(self) -> list[tuple[str, int]]:
        result = [("integer", index) for index in range(len(self._integer_digits))]
        result.extend(("fraction", index) for index in range(len(self._fraction_digits)))
        return result

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._buttons = []
        editable_index = 0
        for index, digit in enumerate(self._integer_digits):
            button = DigitButton(editable_index, digit, self)
            button.digitChanged.connect(self.set_digit)
            self._buttons.append(button)
            self._layout.addWidget(button)
            editable_index += 1

        if self.kind == "price":
            dot_label = QLabel(".")
            dot_label.setObjectName("digit_decimal_point")
            dot_label.setAlignment(Qt.AlignCenter)
            dot_label.setFixedSize(8, 30)
            self._layout.addWidget(dot_label)
            for digit in self._fraction_digits:
                button = DigitButton(editable_index, digit, self)
                button.digitChanged.connect(self.set_digit)
                self._buttons.append(button)
                self._layout.addWidget(button)
                editable_index += 1

        self._update_fixed_width()

    def _refresh(self) -> None:
        digits = self._integer_digits + self._fraction_digits
        for button, digit in zip(self._buttons, digits):
            button.set_digit(digit)

    def _update_fixed_width(self) -> None:
        digit_count = len(self._integer_digits) + len(self._fraction_digits)
        dot_width = 8 if self.kind == "price" else 0
        width = digit_count * 26 + max(0, digit_count - 1) * 2 + dot_width
        self.setFixedWidth(width)
