from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QWidget


class DigitButton(QPushButton):
    digitChanged = Signal(int, str)

    def __init__(self, index: int, digit: str, parent: QWidget | None = None, *, editable: bool = True) -> None:
        super().__init__(digit, parent)
        self.index = index
        self.editable = editable
        self.setObjectName("digit_button")
        self.setFixedSize(26, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setEnabled(editable)

    def set_digit(self, digit: str) -> None:
        self.setText(digit)

    def mousePressEvent(self, event):  # noqa: N802
        if not self.editable:
            event.ignore()
            return
        parent = self.parent()
        if event.button() == Qt.LeftButton:
            if hasattr(parent, "set_cursor_index"):
                parent.set_cursor_index(self.index)
            if hasattr(parent, "show_digit_menu"):
                parent.show_digit_menu()
            return
        if event.button() == Qt.RightButton and hasattr(parent, "show_width_menu"):
            parent.show_width_menu(self.mapToGlobal(event.pos()))
            return
        super().mousePressEvent(event)

    def _digit_menu_pos(self, menu: QMenu):
        menu_width = menu.sizeHint().width()
        button_center = self.mapToGlobal(QPoint(self.width() // 2, self.height()))
        return QPoint(button_center.x() - menu_width // 2, button_center.y())

    def wheelEvent(self, event: QWheelEvent):  # noqa: N802
        event.ignore()


class DigitPopup(QListWidget):
    digitSelected = Signal(str)
    dismissed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("digit_popup")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setMouseTracking(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedWidth(42)
        self._row_height = 28
        for digit in "0123456789":
            item = QListWidgetItem(digit)
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(self.width(), self._row_height))
            self.addItem(item)
        self.setFixedHeight(self.count() * self._row_height + 2)
        self.setCurrentRow(0)
        self.itemClicked.connect(lambda item: self.digitSelected.emit(item.text()))

    def popup_at_digit(self, button: DigitButton) -> None:
        center = button.mapToGlobal(QPoint(button.width() // 2, button.height()))
        self.move(center.x() - self.width() // 2, center.y())
        self.show()
        self.raise_()

    def set_highlight_index(self, index: int) -> None:
        self.setCurrentRow(max(0, min(index, self.count() - 1)))

    def highlighted_digit(self) -> str:
        item = self.currentItem()
        return item.text() if item else "0"

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        self.dismissed.emit(self)


class DigitMenuAction:
    def __init__(self, digit: str, callback: Callable[[str], None]) -> None:
        self._digit = digit
        self._callback = callback

    def text(self) -> str:
        return self._digit

    def trigger(self) -> None:
        self._callback(self._digit)


class DigitInput(QWidget):
    valueChanged = Signal()
    boundaryNavigateRequested = Signal(str)
    keyboardAdvancePastEndRequested = Signal(object)
    _active_cursor_input: DigitInput | None = None

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if kind not in {"price", "shares"}:
            raise ValueError("kind must be 'price' or 'shares'")
        self.kind = kind
        self.default_integer_digits = 3 if kind == "price" else 4
        self.fraction_digits = 2 if kind == "price" else 0
        self._integer_digits = ["0"] * self.default_integer_digits
        self._fraction_digits = ["0"] * self.fraction_digits
        self._cursor = 0
        self._cursor_visible = False
        self._cursor_at_end = False
        self._event_filter_installed = False
        self._active_menu: QWidget | None = None
        self._active_menu_actions: list[DigitMenuAction] = []
        self._menu_highlight_index = 0
        self._buttons: list[DigitButton] = []
        self._separator_width = 8
        self._visual_integer_width: int | None = None

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

    def integer_width(self) -> int:
        return len(self._integer_digits)

    def visual_integer_width(self) -> int:
        return max(len(self._integer_digits), self._visual_integer_width or 0)

    def set_visual_integer_width(self, width: int | None) -> None:
        target_width = None if width is None else max(width, len(self._integer_digits))
        if target_width == self._visual_integer_width:
            return
        self._visual_integer_width = target_width
        self._rebuild()
        self._update_cursor_style()
        self._update_fixed_width()

    def set_integer_width(self, width: int) -> None:
        significant_integer = "".join(self._integer_digits).lstrip("0") or "0"
        target_width = max(width, self.default_integer_digits, len(significant_integer))
        if target_width == len(self._integer_digits):
            return
        while len(self._integer_digits) < target_width:
            self._integer_digits.insert(0, "0")
        while len(self._integer_digits) > target_width:
            self._integer_digits.pop(0)
        self._cursor = min(self._cursor, max(0, len(self._editable_digits()) - 1))
        self._cursor_at_end = False
        self._rebuild()
        self._update_cursor_style()
        self._update_fixed_width()

    def value(self) -> Decimal | int:
        if self.kind == "price":
            return Decimal(self.text())
        return int(self.text())

    def set_value(self, value: Decimal | int | float | str) -> None:
        old_integer_width = len(self._integer_digits)
        if self.kind == "price":
            text = f"{Decimal(str(value)):.2f}"
            integer, fraction = text.split(".")
            self._ensure_integer_width(len(integer))
            self._integer_digits = list(integer.zfill(len(self._integer_digits)))
            self._fraction_digits = list(fraction)
        else:
            integer = str((int(value) // 100) * 100)
            self._ensure_integer_width(len(integer))
            self._integer_digits = list(integer.zfill(len(self._integer_digits)))
        self._cursor = 0
        self._cursor_visible = False
        self._cursor_at_end = False
        if len(self._integer_digits) == old_integer_width:
            self._refresh()
        else:
            self._rebuild()
        self._update_cursor_style()
        self._update_fixed_width()
        self.valueChanged.emit()

    def add_high_digit(self) -> None:
        self._integer_digits.insert(0, "0")
        self._cursor = 0
        self._cursor_visible = False
        self._cursor_at_end = False
        self._rebuild()
        self._update_cursor_style()
        self._update_fixed_width()
        self.valueChanged.emit()

    def remove_high_digit(self) -> None:
        if len(self._integer_digits) <= self.default_integer_digits:
            return
        self._integer_digits.pop(0)
        self._cursor = 0
        self._cursor_visible = False
        self._cursor_at_end = False
        self._rebuild()
        self._update_cursor_style()
        self._update_fixed_width()
        self.valueChanged.emit()

    def can_remove_high_digit(self) -> bool:
        return len(self._integer_digits) > self.default_integer_digits

    def show_width_menu(self, global_pos) -> None:
        menu = QMenu(self)
        add_action = QAction("增加最高位", menu)
        add_action.triggered.connect(self.add_high_digit)
        menu.addAction(add_action)
        remove_action = QAction("删除最高位", menu)
        remove_action.setEnabled(self.can_remove_high_digit())
        remove_action.triggered.connect(self.remove_high_digit)
        menu.addAction(remove_action)
        menu.exec(global_pos)

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
        self._update_cursor_style()
        self.valueChanged.emit()

    def set_cursor_index(self, index: int) -> None:
        if DigitInput._active_cursor_input and DigitInput._active_cursor_input is not self:
            DigitInput._active_cursor_input.clear_cursor()
        self._cursor = max(0, min(index, len(self._editable_digits()) - 1))
        self._cursor_visible = True
        DigitInput._active_cursor_input = self
        self._cursor_at_end = False
        self.setFocus(Qt.MouseFocusReason)
        self._install_cursor_event_filter()
        self._update_cursor_style()

    def clear_cursor(self) -> None:
        if not self._cursor_visible:
            return
        self.hide_digit_menu()
        self._cursor_visible = False
        if DigitInput._active_cursor_input is self:
            DigitInput._active_cursor_input = None
        self._cursor_at_end = False
        self._remove_cursor_event_filter()
        self._update_cursor_style()

    def set_active_menu(self, menu: QWidget | None) -> None:
        self._active_menu = menu

    def show_digit_menu(self) -> None:
        if not self._cursor_visible:
            self.set_cursor_index(self._cursor)
        self.hide_digit_menu()
        button = self._button_for_cursor()
        if button is None:
            return
        menu = DigitPopup(self)
        menu.digitSelected.connect(self._apply_menu_digit)
        actions = [DigitMenuAction(digit, self._apply_menu_digit) for digit in "0123456789"]
        self._active_menu_actions = actions
        self._menu_highlight_index = 0
        self.set_active_menu(menu)
        menu.dismissed.connect(self._clear_active_menu)
        menu.popup_at_digit(button)
        menu.set_highlight_index(0)

    def hide_digit_menu(self) -> None:
        if self._active_menu:
            self._active_menu.close()
            self._clear_active_menu(self._active_menu)

    def move_to_first_digit(self) -> None:
        self.hide_digit_menu()
        self.set_cursor_index(0)

    def move_to_last_digit(self) -> None:
        self.hide_digit_menu()
        self.set_cursor_index(len(self._editable_digits()) - 1)

    def eventFilter(self, watched, event):  # noqa: N802
        if (
            event.type() == QEvent.KeyPress
            and self._cursor_visible
            and self._active_menu
            and watched is not self
            and self._handle_cursor_key(event)
        ):
            return True
        if event.type() == QEvent.MouseButtonPress and self._cursor_visible:
            target = QApplication.widgetAt(event.globalPosition().toPoint())
            if target is None:
                self.clear_cursor()
            elif self._active_menu and (target is self._active_menu or self._active_menu.isAncestorOf(target)):
                return False
            elif target is not self and not self.isAncestorOf(target):
                self.clear_cursor()
        return super().eventFilter(watched, event)

    def is_valid(self) -> bool:
        value = self.value()
        if self.kind == "price":
            return isinstance(value, Decimal) and value > 0
        return isinstance(value, int) and value > 0 and value % 100 == 0

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if self._cursor_visible and self._handle_cursor_key(event):
            return
        super().keyPressEvent(event)

    def event(self, event):  # noqa: N802
        if event.type() == QEvent.DeferredDelete:
            self._cleanup_cursor_state()
        return super().event(event)

    def _handle_cursor_key(self, event: QKeyEvent) -> bool:
        text = event.text()
        if text and text in "0123456789":
            self.hide_digit_menu()
            self._apply_keyboard_digit(text)
            event.accept()
            return True
        if event.key() == Qt.Key_Left:
            self.hide_digit_menu()
            if self._cursor <= 0:
                self.boundaryNavigateRequested.emit("left")
            else:
                self.set_cursor_index(self._cursor - 1)
            event.accept()
            return True
        if event.key() == Qt.Key_Right:
            self.hide_digit_menu()
            if self._cursor >= len(self._editable_digits()) - 1:
                self.boundaryNavigateRequested.emit("right")
            else:
                self.set_cursor_index(self._cursor + 1)
            event.accept()
            return True
        if event.key() == Qt.Key_Down:
            if self._active_menu and self._active_menu_actions:
                self._set_menu_highlight(min(self._menu_highlight_index + 1, len(self._active_menu_actions) - 1))
            else:
                self.show_digit_menu()
                self._set_menu_highlight(0)
            event.accept()
            return True
        if event.key() == Qt.Key_Up and self._active_menu and self._active_menu_actions:
            if self._menu_highlight_index <= 0:
                self.hide_digit_menu()
            else:
                self._set_menu_highlight(self._menu_highlight_index - 1)
            event.accept()
            return True
        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and self._active_menu and self._active_menu_actions:
            self._active_menu_actions[self._menu_highlight_index].trigger()
            event.accept()
            return True
        if event.key() in {Qt.Key_Backspace, Qt.Key_Delete}:
            self.hide_digit_menu()
            self._cursor_at_end = False
            self.set_digit(self._cursor, "0")
            event.accept()
            return True
        return False

    def _ensure_integer_width(self, width: int) -> None:
        while len(self._integer_digits) < max(width, self.default_integer_digits):
            self._integer_digits.insert(0, "0")

    def _editable_digits(self) -> list[tuple[str, int]]:
        integer_limit = len(self._integer_digits) - 2 if self.kind == "shares" else len(self._integer_digits)
        result = [("integer", index) for index in range(max(0, integer_limit))]
        result.extend(("fraction", index) for index in range(len(self._fraction_digits)))
        return result

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setObjectName("")
                widget.deleteLater()

        self._buttons = []
        editable_index = 0
        visual_integer_width = self.visual_integer_width()
        leading_placeholder_count = visual_integer_width - len(self._integer_digits)
        for visual_index in range(visual_integer_width):
            integer_index = visual_index - leading_placeholder_count
            if integer_index < 0:
                placeholder = QWidget(self)
                placeholder.setObjectName("digit_alignment_placeholder")
                placeholder.setFixedSize(26, 30)
                self._layout.addWidget(placeholder)
            else:
                digit = self._integer_digits[integer_index]
                editable = self.kind != "shares" or integer_index < len(self._integer_digits) - 2
                button = DigitButton(editable_index if editable else -1, digit, self, editable=editable)
                if editable:
                    button.digitChanged.connect(self.set_digit)
                    editable_index += 1
                self._buttons.append(button)
                self._layout.addWidget(button)
            if self._has_thousands_separator_after(visual_index, visual_integer_width):
                if integer_index < 0:
                    separator = QWidget(self)
                    separator.setObjectName("digit_thousands_separator_placeholder")
                else:
                    separator = QLabel(",")
                    separator.setObjectName("digit_thousands_separator")
                    separator.setAlignment(Qt.AlignCenter)
                separator.setFixedSize(self._separator_width, 30)
                self._layout.addWidget(separator)

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
        self._update_cursor_style()

    def _refresh(self) -> None:
        digits = self._integer_digits + self._fraction_digits
        for button, digit in zip(self._buttons, digits):
            button.set_digit(digit)

    def _apply_menu_digit(self, digit: str) -> None:
        self.hide_digit_menu()
        self.set_digit(self._cursor, digit)
        self.set_cursor_index(self._cursor)

    def _apply_keyboard_digit(self, digit: str) -> None:
        editable_count = len(self._editable_digits())
        if self._cursor_at_end:
            return
        self.set_digit(self._cursor, digit)
        if self._cursor < editable_count - 1:
            self.set_cursor_index(self._cursor + 1)
            return
        self.keyboardAdvancePastEndRequested.emit(self)
        if DigitInput._active_cursor_input is self:
            self._finish_keyboard_entry()

    def _finish_keyboard_entry(self) -> None:
        self.hide_digit_menu()
        self._cursor_visible = False
        if DigitInput._active_cursor_input is self:
            DigitInput._active_cursor_input = None
        self._cursor_at_end = True
        self._remove_cursor_event_filter()
        self._update_cursor_style()

    def _set_menu_highlight(self, index: int) -> None:
        if not self._active_menu_actions:
            return
        self._menu_highlight_index = max(0, min(index, len(self._active_menu_actions) - 1))
        if isinstance(self._active_menu, DigitPopup):
            self._active_menu.set_highlight_index(self._menu_highlight_index)

    def _clear_active_menu(self, menu: QWidget) -> None:
        if self._active_menu is not menu:
            return
        self._active_menu = None
        self._active_menu_actions = []
        self._menu_highlight_index = 0

    def _button_for_cursor(self) -> DigitButton | None:
        for button in self._buttons:
            if button.editable and button.index == self._cursor:
                return button
        return None

    def _has_thousands_separator_after(self, integer_index: int, width: int | None = None) -> bool:
        integer_width = len(self._integer_digits) if width is None else width
        digits_to_right = integer_width - integer_index - 1
        return digits_to_right > 0 and digits_to_right % 3 == 0

    def _thousands_separator_count(self) -> int:
        return max(0, (self.visual_integer_width() - 1) // 3)

    def _update_cursor_style(self) -> None:
        for button in self._buttons:
            button.setProperty("digitCursor", self._cursor_visible and button.editable and button.index == self._cursor)
            button.style().unpolish(button)
            button.style().polish(button)

    def _install_cursor_event_filter(self) -> None:
        app = QApplication.instance()
        if app and not self._event_filter_installed:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _remove_cursor_event_filter(self) -> None:
        app = QApplication.instance()
        if app and self._event_filter_installed:
            app.removeEventFilter(self)
            self._event_filter_installed = False

    def _update_fixed_width(self) -> None:
        digit_count = self.visual_integer_width() + len(self._fraction_digits)
        separator_count = self._thousands_separator_count()
        dot_width = 8 if self.kind == "price" else 0
        widget_count = digit_count + separator_count + (1 if self.kind == "price" else 0)
        width = digit_count * 26 + separator_count * self._separator_width + dot_width
        width += max(0, widget_count - 1) * self._layout.spacing()
        self.setFixedWidth(width)

    def _cleanup_cursor_state(self) -> None:
        self.hide_digit_menu()
        self._remove_cursor_event_filter()
        if DigitInput._active_cursor_input is self:
            DigitInput._active_cursor_input = None
