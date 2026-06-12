from decimal import Decimal

from PySide6.QtCore import Qt

from ptrade_order_tool.ui.digit_input import DigitInput


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


def test_width_menu_delete_is_disabled_at_default_width(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)

    assert widget.can_remove_high_digit() is False

    widget.add_high_digit()
    assert widget.can_remove_high_digit() is True


def test_keyboard_input_fills_digits_left_to_right(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.setFocus()

    qtbot.keyClicks(widget, "12345")

    assert widget.text() == "123.45"


def test_keyboard_cursor_is_visible_and_moves_after_input(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.setFocus()

    assert widget._buttons[0].property("digitCursor") is True

    qtbot.keyClicks(widget, "1")
    assert widget.text() == "100.00"
    assert widget._buttons[1].property("digitCursor") is True

    qtbot.keyClick(widget, Qt.Key_Left)
    assert widget._buttons[0].property("digitCursor") is True

    qtbot.keyClicks(widget, "9")
    assert widget.text() == "900.00"
    assert widget._buttons[1].property("digitCursor") is True


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

    qtbot.keyClicks(widget, "1234")

    assert widget.text() == "1200"
    assert widget._buttons[1].property("digitCursor") is True
