from PySide6.QtCore import QRect


def popup_vertical_position(*, anchor_top: int, anchor_bottom: int, popup_height: int, available: QRect) -> int:
    if anchor_bottom + popup_height <= available.bottom() + 1:
        return anchor_bottom
    if anchor_top - popup_height >= available.top():
        return anchor_top - popup_height
    return max(available.top(), min(anchor_bottom, available.bottom() - popup_height + 1))
