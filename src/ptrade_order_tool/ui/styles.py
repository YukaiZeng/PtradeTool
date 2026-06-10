from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APP_STYLESHEET = """
QMainWindow {
    background: #f6f7f9;
    font-size: 13px;
}

QLabel {
    color: #172033;
}

QLabel#account_total_label,
QLabel#account_stock_value_label,
QLabel#account_cash_label,
QLabel#account_opening_amount_label,
QLabel#draft_summary_label {
    background: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 6px;
    color: #172033;
    font-weight: 700;
    min-width: 118px;
    padding: 6px 10px;
}

QLabel#account_stock_value_label {
    color: #047857;
}

QLabel#account_cash_label {
    color: #334155;
}

QLabel#account_opening_amount_label {
    color: #2563eb;
}

QLabel#draft_summary_label {
    color: #667085;
    min-width: 150px;
}

QLabel#startup_status_label {
    color: #667085;
    font-weight: 600;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    color: #172033;
    min-height: 28px;
    padding: 4px 10px;
}

QPushButton:hover {
    background: #f1f5f9;
    border-color: #b8c2d1;
}

QPushButton:disabled {
    background: #eef1f5;
    border-color: #d9dee7;
    color: #98a2b3;
}

QPushButton#export_button {
    background: #172033;
    border-color: #172033;
    color: #ffffff;
    font-weight: 800;
}

QPushButton#export_button:hover {
    background: #26344d;
}

QPushButton#check_export_button {
    border-color: #94a3b8;
    color: #172033;
    font-weight: 700;
}

QPushButton#add_stock_button,
QPushButton#manual_import_button,
QPushButton#locate_unconfirmed_button {
    font-weight: 700;
}

QPushButton#locate_unconfirmed_button {
    background: #fff7ed;
    border-color: #fed7aa;
    color: #c2410c;
}

QPushButton#open_export_dir_button {
    color: #334155;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    color: #172033;
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
    background: #eef2f7;
    border: 1px solid #d2d9e5;
    border-radius: 6px;
    color: #667085;
    margin-right: 6px;
    padding: 6px 14px;
}

QTabBar::tab:selected {
    background: #ffffff;
    border-color: #aeb8c8;
    color: #172033;
    font-weight: 800;
}

QScrollArea {
    border: 0;
}

QFrame[frameShape="6"] {
    background: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 8px;
}

QLabel#stock_card_header {
    color: #172033;
    font-size: 16px;
    font-weight: 800;
}

QLabel#stock_type_badge,
QLabel#pending_order_badge,
QLabel#order_status_label {
    border-radius: 6px;
    font-size: 12px;
    font-weight: 800;
    padding: 3px 8px;
}

QLabel#stock_type_badge[kind="holding"] {
    background: #ecfdf3;
    color: #047857;
}

QLabel#stock_type_badge[kind="opening"] {
    background: #eff6ff;
    color: #1d4ed8;
}

QLabel#pending_order_badge {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    color: #c2410c;
}

QLabel#stock_metric_chip {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #334155;
    font-weight: 700;
    padding: 4px 8px;
}

QLabel#stock_metric_chip[tone="negative"] {
    background: #fff1f2;
    border-color: #fecdd3;
    color: #b42318;
}

QLabel#stock_metric_chip[tone="positive"] {
    background: #ecfdf3;
    border-color: #bbf7d0;
    color: #047857;
}

QWidget#stock_card_warning_box {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 6px;
}

QLabel#stock_card_warning {
    color: #c2410c;
    font-weight: 700;
}

QGroupBox {
    background: #fbfcfe;
    border: 1px solid #d8dee8;
    border-radius: 6px;
    color: #172033;
    font-weight: 800;
    margin-top: 8px;
    padding: 8px;
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

QWidget#order_row {
    background: #ffffff;
    border-left: 4px solid #94a3b8;
}

QWidget#order_row[side="buy"] {
    border-left: 4px solid #2563eb;
}

QWidget#order_row[side="sell_profit"] {
    border-left: 4px solid #dc2626;
}

QWidget#order_row[side="sell_loss"] {
    border-left: 4px solid #ea580c;
}

QComboBox#order_type_combo {
    font-weight: 700;
}

QComboBox#order_type_combo[side="buy"] {
    color: #2563eb;
}

QComboBox#order_type_combo[side="sell_profit"] {
    color: #dc2626;
}

QComboBox#order_type_combo[side="sell_loss"] {
    color: #ea580c;
}

QLabel#order_status_label[status="pending"] {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    color: #c2410c;
}

QLabel#order_status_label[status="inherited"] {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    color: #1d4ed8;
}

QLabel#order_status_label[status="confirmed"] {
    background: #ecfdf3;
    border: 1px solid #bbf7d0;
    color: #047857;
}

QPushButton#order_confirm_button[status="pending"],
QPushButton#order_confirm_button[status="inherited"] {
    background: #172033;
    border-color: #172033;
    color: #ffffff;
    font-weight: 800;
}

QPushButton#order_confirm_button[status="confirmed"] {
    background: #ecfdf3;
    border-color: #bbf7d0;
    color: #047857;
    font-weight: 800;
}

QPushButton#order_delete_button {
    color: #667085;
}

QPushButton[role="add_order"] {
    color: #334155;
    font-weight: 700;
    min-width: 58px;
}

QLabel#order_field_label {
    color: #667085;
    font-size: 12px;
    font-weight: 700;
}

QLabel#order_amount_label {
    color: #334155;
    font-weight: 800;
    padding-left: 6px;
}

QPushButton#digit_button {
    background: #ffffff;
    border: 1px solid #d7dee9;
    border-radius: 5px;
    color: #172033;
    font-size: 13px;
    font-weight: 700;
    min-height: 0;
    min-width: 0;
    padding: 0;
}

QPushButton#digit_button:hover {
    background: #eff6ff;
    border-color: #93c5fd;
}

QLabel#digit_decimal_point {
    color: #667085;
    font-size: 18px;
    font-weight: 800;
    padding-top: 8px;
}

QLabel#empty_order_label {
    background: #f8fafc;
    border: 1px dashed #d6dde7;
    border-radius: 6px;
    color: #98a2b3;
    padding: 10px;
}

QLabel#empty_state_label {
    background: #ffffff;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    color: #667085;
    font-size: 15px;
    font-weight: 700;
    padding: 28px;
}

QWidget#export_check_section {
    background: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 6px;
}

QWidget#export_check_section[tone="blocker"] {
    background: #fff1f2;
    border-color: #fecdd3;
}

QWidget#export_check_section[tone="warning"] {
    background: #fff7ed;
    border-color: #fed7aa;
}

QWidget#export_check_section[tone="pending"] {
    background: #eff6ff;
    border-color: #bfdbfe;
}

QLabel#export_check_summary {
    color: #172033;
    font-size: 14px;
    font-weight: 800;
}

QLabel#export_check_section_title {
    color: #172033;
    font-weight: 800;
}

QLabel#export_check_item {
    color: #334155;
    font-weight: 600;
}
"""


def apply_app_style(app: QApplication) -> None:
    app.setFont(QFont("Arial", 13))
    app.setStyleSheet(APP_STYLESHEET)
