from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APP_STYLESHEET = """
QMainWindow {
    background: #f4f6f8;
    font-size: 13px;
}

QLabel {
    color: #1f2933;
}

QLabel#account_total_label,
QLabel#account_stock_value_label,
QLabel#account_cash_label,
QLabel#account_opening_amount_label,
QLabel#draft_summary_label {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}

QLabel#account_total_label {
    color: #111827;
}

QLabel#account_stock_value_label {
    color: #0f766e;
}

QLabel#account_cash_label {
    color: #7c3aed;
}

QLabel#account_opening_amount_label {
    color: #2563eb;
}

QLabel#draft_summary_label {
    color: #475569;
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
    background: #0f172a;
    border-color: #0f172a;
    color: #ffffff;
    font-weight: 700;
}

QPushButton#export_button:hover {
    background: #1f2937;
}

QPushButton:hover {
    background: #eef2f7;
}

QPushButton#add_stock_button,
QPushButton#manual_import_button {
    font-weight: 600;
}

QPushButton:disabled {
    background: #eef0f3;
    color: #8a929c;
}

QPushButton#digit_button {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    color: #0f172a;
    font-size: 13px;
    font-weight: 600;
    min-height: 0;
    min-width: 0;
    padding: 0;
}

QPushButton#digit_button:hover {
    background: #eff6ff;
    border-color: #93c5fd;
}

QLabel#digit_decimal_point {
    color: #475569;
    font-size: 18px;
    font-weight: 700;
    padding-top: 8px;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #c9ced6;
    border-radius: 6px;
    color: #20242a;
    min-height: 28px;
    padding: 3px 8px;
}

QLineEdit#stock_search_input {
    min-height: 30px;
}

QTabWidget::pane {
    border: 0;
}

QTabBar::tab {
    background: #e9edf2;
    border: 1px solid #c9ced6;
    border-radius: 6px;
    margin-right: 6px;
    padding: 6px 14px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #111827;
    font-weight: 700;
}

QFrame[frameShape="6"] {
    background: #ffffff;
    border: 1px solid #d9e0e8;
    border-radius: 8px;
}

QLabel#stock_card_header {
    color: #101828;
    font-size: 16px;
    font-weight: 800;
}

QLabel#stock_type_badge {
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#stock_type_badge[kind="holding"] {
    background: #e8f5f0;
    color: #047857;
}

QLabel#stock_type_badge[kind="opening"] {
    background: #eff6ff;
    color: #1d4ed8;
}

QLabel#pending_order_badge {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 6px;
    color: #c2410c;
    font-size: 12px;
    font-weight: 700;
    padding: 3px 8px;
}

QLabel#stock_metric_chip {
    background: #f8fafc;
    border: 1px solid #e1e7ef;
    border-radius: 6px;
    color: #334155;
    padding: 4px 8px;
    font-weight: 600;
}

QLabel#stock_metric_chip[tone="negative"] {
    background: #fff1f2;
    border-color: #fecdd3;
    color: #be123c;
}

QLabel#stock_metric_chip[tone="positive"] {
    background: #ecfdf3;
    border-color: #bbf7d0;
    color: #15803d;
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

QLabel#empty_order_label {
    background: #f8fafc;
    border: 1px dashed #d6dde7;
    border-radius: 6px;
    color: #94a3b8;
    padding: 10px;
}

QGroupBox {
    background: #fbfcfe;
    border: 1px solid #d8dde5;
    border-radius: 6px;
    margin-top: 8px;
    padding: 8px;
    font-weight: 700;
    color: #1f2933;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QGroupBox[side="buy"] {
    border-top: 3px solid #2563eb;
}

QGroupBox[side="sell_profit"] {
    border-top: 3px solid #dc2626;
}

QGroupBox[side="sell_loss"] {
    border-top: 3px solid #ea580c;
}

QLabel#startup_status_label {
    color: #5b6470;
    font-weight: 600;
}

QLabel#empty_state_label {
    background: #ffffff;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    color: #64748b;
    font-size: 15px;
    font-weight: 600;
    padding: 28px;
}
"""


def apply_app_style(app: QApplication) -> None:
    app.setFont(QFont("Arial", 13))
    app.setStyleSheet(APP_STYLESHEET)
