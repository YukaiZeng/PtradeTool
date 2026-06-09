from decimal import Decimal

from ptrade_order_tool.ui.digit_input import DigitInput


def test_price_input_defaults_to_four_digits_and_two_decimals(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)

    assert widget.text() == "0000.00"
    assert widget.value() == Decimal("0.00")
    assert widget.is_valid() is False


def test_share_input_defaults_to_four_digits(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    assert widget.text() == "0000"
    assert widget.value() == 0
    assert widget.is_valid() is False


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


def test_keyboard_input_fills_digits_left_to_right(qtbot):
    widget = DigitInput("price")
    qtbot.addWidget(widget)
    widget.setFocus()

    qtbot.keyClicks(widget, "123456")

    assert widget.text() == "1234.56"


def test_share_validation_requires_hundred_lot(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    widget.set_value(1200)
    assert widget.is_valid() is True

    widget.set_value(1250)
    assert widget.is_valid() is False


def test_digit_button_signal_changes_digit(qtbot):
    widget = DigitInput("shares")
    qtbot.addWidget(widget)

    widget._buttons[0].digitChanged.emit(0, "1")

    assert widget.text() == "1000"
