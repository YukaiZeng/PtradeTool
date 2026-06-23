from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMenu, QPushButton

from ptrade_order_tool.models import OrderDraft
from ptrade_order_tool.ui.digit_input import DigitInput
from ptrade_order_tool.ui.order_row import OrderRow


def test_price_input_defaults_to_three_digits_and_two_decimals(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)

    assert widget.text() == "000.00"
    assert widget.value() == Decimal("0.00")
    assert widget.is_valid() is False
    assert widget._buttons[0].width() == 26
    assert widget._buttons[0].height() == 30


def test_share_input_defaults_to_four_digits(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    assert widget.text() == "0000"
    assert widget.value() == 0
    assert widget.is_valid() is False
    assert widget._buttons[-1].isEnabled() is False
    assert widget._buttons[-2].isEnabled() is False


def test_add_and_remove_high_digit_shifts_existing_digits(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.set_value("1234.56")

    widget.add_high_digit()
    assert widget.text() == "01234.56"

    widget.set_digit(0, "9")
    assert widget.text() == "91234.56"

    widget.remove_high_digit()
    assert widget.text() == "1234.56"


def test_digit_input_displays_thousands_separators_without_changing_value(qtbot):
    price = DigitInput("price")
    shares = DigitInput("shares")
    qtbot.addWidget(price)
    qtbot.addWidget(shares)

    price.set_value("1234.56")
    shares.set_value(32000)

    assert price.text() == "1234.56"
    assert price.value() == Decimal("1234.56")
    assert [label.text() for label in price.findChildren(QLabel, "digit_thousands_separator")] == [","]
    assert shares.text() == "32000"
    assert shares.value() == 32000
    assert [label.text() for label in shares.findChildren(QLabel, "digit_thousands_separator")] == [","]
    assert len(price._buttons) == 6
    assert len(shares._buttons) == 5


def test_width_menu_delete_is_disabled_at_default_width(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)

    assert widget.can_remove_high_digit() is False

    widget.add_high_digit()
    assert widget.can_remove_high_digit() is True


def test_keyboard_input_requires_visible_cursor(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.setFocus()

    qtbot.keyClicks(widget, "12345")

    assert widget.text() == "000.00"

    widget.set_cursor_index(0)
    qtbot.keyClicks(widget, "12345")

    assert widget.text() == "123.45"


def test_keyboard_cursor_is_visible_and_moves_after_input(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.setFocus()

    assert all(button.property("digitCursor") in {False, None} for button in widget._buttons)
    widget.set_cursor_index(0)
    assert widget._buttons[0].property("digitCursor") is True

    qtbot.keyClicks(widget, "1")
    assert widget.text() == "100.00"
    assert widget._buttons[1].property("digitCursor") is True

    qtbot.keyClick(widget, Qt.Key_Left)
    assert widget._buttons[0].property("digitCursor") is True

    qtbot.keyClicks(widget, "9")
    assert widget.text() == "900.00"
    assert widget._buttons[1].property("digitCursor") is True


def test_digit_menu_opens_aligned_below_clicked_digit(qtbot, monkeypatch):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    button = widget._buttons[1]
    menu = QMenu(button)
    menu.addAction("0")

    widget.set_cursor_index(1)
    expected = button.mapToGlobal(button.rect().topLeft())
    expected.setX(expected.x() + button.width() // 2 - menu.sizeHint().width() // 2)
    expected.setY(expected.y() + button.height())

    assert widget._buttons[1].property("digitCursor") is True
    assert button._digit_menu_pos(menu) == expected


def test_cursor_is_cleared_when_clicking_outside_digit_input(qtbot):
    widget = DigitInput("price")
    outside = QPushButton("outside")
    qtbot.addWidget(widget)
    qtbot.addWidget(outside)
    widget.show()
    outside.show()

    widget.set_cursor_index(1)
    assert widget._buttons[1].property("digitCursor") is True

    qtbot.mouseClick(outside, Qt.LeftButton)

    assert all(button.property("digitCursor") is False for button in widget._buttons)


def test_only_one_digit_input_shows_cursor_at_a_time(qtbot):
    first = DigitInput("price")
    second = DigitInput("shares")
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    first.set_cursor_index(1)
    second.set_cursor_index(0)

    assert all(button.property("digitCursor") is False for button in first._buttons)
    assert second._buttons[0].property("digitCursor") is True


def test_backspace_and_delete_reset_current_digit_without_moving_cursor(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.set_value("1234.56")
    widget.set_cursor_index(2)
    widget.setFocus()

    qtbot.keyClick(widget, Qt.Key_Backspace)

    assert widget.text() == "1204.56"
    assert widget._buttons[2].property("digitCursor") is True

    widget.set_value("1234.56")
    widget.set_cursor_index(3)
    qtbot.keyClick(widget, Qt.Key_Delete)

    assert widget.text() == "1230.56"
    assert widget._buttons[3].property("digitCursor") is True


def test_mouse_wheel_does_not_change_digits(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)
    widget.set_value(1200)

    class FakeWheelEvent:
        def ignore(self):
            self.ignored = True

    event = FakeWheelEvent()
    widget._buttons[1].wheelEvent(event)

    assert widget.text() == "1200"
    assert event.ignored is True


def test_share_validation_requires_hundred_lot(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    widget.set_value(1200)
    assert widget.is_valid() is True

    widget.set_value(1250)
    assert widget.text() == "1200"
    assert widget.is_valid() is True


def test_digit_button_signal_changes_digit(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    widget._buttons[0].digitChanged.emit(0, "1")

    assert widget.text() == "1000"


def test_share_last_two_digits_are_locked(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)
    widget.set_value(1200)

    widget.set_digit(0, "9")

    assert widget.text() == "9200"
    assert widget._buttons[-1].index == -1
    assert widget._buttons[-2].index == -1


def test_share_keyboard_skips_locked_last_two_digits(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)
    widget.setFocus()

    qtbot.keyClicks(widget, "99")
    assert widget.text() == "0000"

    widget.set_cursor_index(0)
    qtbot.keyClicks(widget, "1234")

    assert widget.text() == "1200"
    assert all(button.property("digitCursor") is False for button in widget._buttons)

    qtbot.keyClick(widget, Qt.Key_9)
    assert widget.text() == "1200"


def test_digit_menu_keyboard_digit_fills_and_hides_menu(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.set_cursor_index(0)
    widget.show_digit_menu()

    assert widget._active_menu is not None
    qtbot.keyClick(widget, Qt.Key_7)

    assert widget.text() == "700.00"
    assert widget._active_menu is None
    assert widget._buttons[1].property("digitCursor") is True


def test_digit_menu_click_or_enter_keeps_cursor_on_current_digit(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.set_cursor_index(1)
    widget.show_digit_menu()

    widget._active_menu_actions[5].trigger()

    assert widget.text() == "050.00"
    assert widget._active_menu is None
    assert widget._buttons[1].property("digitCursor") is True

    widget.show_digit_menu()
    widget._set_menu_highlight(3)
    qtbot.keyClick(widget, Qt.Key_Return)

    assert widget.text() == "030.00"
    assert widget._active_menu is None
    assert widget._buttons[1].property("digitCursor") is True


def test_digit_menu_arrow_keys_hide_or_move_highlight(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.set_cursor_index(1)
    widget.show_digit_menu()

    qtbot.keyClick(widget, Qt.Key_Right)

    assert widget._active_menu is None
    assert widget._buttons[2].property("digitCursor") is True

    qtbot.keyClick(widget, Qt.Key_Down)
    assert widget._active_menu is not None
    assert widget._menu_highlight_index == 0

    qtbot.keyClick(widget, Qt.Key_Up)
    assert widget._active_menu is None


def test_order_row_arrow_keys_jump_between_price_and_shares(qtbot):
    row = OrderRow(OrderDraft("buy_limit", Decimal("1.23"), 1200))
    qtbot.addWidget(row)

    row.price_input.move_to_last_digit()
    qtbot.keyClick(row.price_input, Qt.Key_Right)

    assert row.shares_input._buttons[0].property("digitCursor") is True

    qtbot.keyClick(row.shares_input, Qt.Key_Left)

    assert row.price_input._buttons[-1].property("digitCursor") is True


def test_order_row_keyboard_digit_advances_from_price_end_to_shares_start(qtbot):
    row = OrderRow(OrderDraft("buy_limit", Decimal("1.23"), 1200))
    qtbot.addWidget(row)

    row.price_input.move_to_last_digit()
    qtbot.keyClick(row.price_input, Qt.Key_9)

    assert row.price_input.text() == "001.29"
    assert row.shares_input._buttons[0].property("digitCursor") is True


def test_order_row_arrow_keys_jump_between_adjacent_rows(qtbot):
    first = OrderRow(OrderDraft("buy_limit", Decimal("1.23"), 1200))
    second = OrderRow(OrderDraft("buy_limit", Decimal("2.34"), 2300))
    first.set_adjacent_rows(None, second)
    second.set_adjacent_rows(first, None)
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    first.shares_input.move_to_last_digit()
    qtbot.keyClick(first.shares_input, Qt.Key_Right)

    assert second.price_input._buttons[0].property("digitCursor") is True

    qtbot.keyClick(second.price_input, Qt.Key_Left)

    assert first.shares_input._buttons[1].property("digitCursor") is True


def test_order_row_keyboard_digit_advances_to_next_row_or_clears_at_last_row(qtbot):
    first = OrderRow(OrderDraft("buy_limit", Decimal("1.23"), 1200))
    second = OrderRow(OrderDraft("buy_limit", Decimal("2.34"), 2300))
    first.set_adjacent_rows(None, second)
    second.set_adjacent_rows(first, None)
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    first.shares_input.move_to_last_digit()
    qtbot.keyClick(first.shares_input, Qt.Key_8)

    assert first.shares_input.text() == "1800"
    assert second.price_input._buttons[0].property("digitCursor") is True

    second.shares_input.move_to_last_digit()
    qtbot.keyClick(second.shares_input, Qt.Key_7)

    assert second.shares_input.text() == "2700"
    assert all(button.property("digitCursor") is False for button in second.shares_input._buttons)
