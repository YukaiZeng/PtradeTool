from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APP_STYLESHEET = """
QMainWindow {
    background: #f6f7f9;
    font-size: 13px;
}

QLabel {
    color: #20242a;
}

QLabel#account_total_label,
QLabel#account_stock_value_label,
QLabel#account_cash_label {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #c9ced6;
    border-radius: 6px;
    color: #20242a;
    min-height: 28px;
    padding: 4px 10px;
}

QPushButton#export_button {
    background: #111827;
    border-color: #111827;
    color: #ffffff;
    font-weight: 700;
}

QPushButton#export_button:hover {
    background: #1f2937;
}

QPushButton:hover {
    background: #eef2f7;
}

QPushButton:disabled {
    background: #eef0f3;
    color: #8a929c;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #c9ced6;
    border-radius: 6px;
    color: #20242a;
    min-height: 28px;
    padding: 3px 8px;
}

QTabWidget::pane {
    border: 0;
}

QTabBar::tab {
    background: #e8ebef;
    border: 1px solid #c9ced6;
    border-radius: 6px;
    margin-right: 6px;
    padding: 6px 14px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #111827;
    font-weight: 600;
}

QFrame[frameShape="6"] {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 8px;
}

QWidget#stock_card_warning_box {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 6px;
}

QLabel#stock_card_warning {
    color: #c2410c;
    font-weight: 600;
}

QGroupBox {
    border: 1px solid #d8dde5;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QLabel#startup_status_label {
    color: #5b6470;
}
"""


def apply_app_style(app: QApplication) -> None:
    app.setFont(QFont("Arial", 13))
    app.setStyleSheet(APP_STYLESHEET)
