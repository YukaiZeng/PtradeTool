from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
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
    padding: 5px 8px;
}

QWidget#top_tool_panel {
    background: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 8px;
}

QLabel#account_stock_value_label {
    color: #172033;
}

QLabel#account_cash_label {
    color: #172033;
}

QLabel#account_opening_amount_label {
    color: #172033;
}

QLabel#draft_summary_label {
    color: #667085;
}

QLabel#startup_status_label {
    color: #667085;
    font-weight: 600;
}

QLabel#action_separator {
    color: #c0c8d4;
    font-weight: 700;
    padding: 0 2px;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    color: #172033;
    min-height: 28px;
    padding: 4px 9px;
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

QPushButton#export_button:disabled {
    background: #eef1f5;
    border-color: #d9dee7;
    color: #98a2b3;
}

QPushButton#check_export_button {
    border-color: #94a3b8;
    color: #172033;
    font-weight: 700;
}

QPushButton#check_export_button[tone="blocker"] {
    background: #fff1f2;
    border-color: #fda4af;
    color: #c1121f;
}

QPushButton#check_export_button[tone="blocker"]:hover {
    background: #ffe4e6;
    border-color: #fb7185;
}

QPushButton#check_export_button[tone="warning"] {
    background: #fff7ed;
    border-color: #fdba74;
    color: #c2410c;
}

QPushButton#check_export_button[tone="warning"]:hover {
    background: #ffedd5;
    border-color: #fb923c;
}

QPushButton#check_export_button[tone="pending"] {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
}

QPushButton#check_export_button[tone="pending"]:hover {
    background: #dbeafe;
    border-color: #60a5fa;
}

QPushButton#check_export_button[tone="clean"] {
    background: #ffffff;
    border-color: #94a3b8;
    color: #172033;
}

QPushButton#check_export_button[tone="clean"]:hover {
    background: #f1f5f9;
    border-color: #64748b;
}

QPushButton#add_stock_button,
QPushButton#manual_import_button,
QPushButton#locate_unconfirmed_button {
    font-weight: 700;
}

QPushButton#locate_unconfirmed_button:enabled {
    background: #fff7ed;
    border-color: #fed7aa;
    color: #c2410c;
}

QPushButton#locate_unconfirmed_button:enabled:hover {
    background: #ffedd5;
    border-color: #fb923c;
}

QPushButton#open_export_dir_button {
    color: #334155;
}

QPushButton#more_actions_button {
    font-weight: 700;
}

QPushButton[role="delete_stock"] {
    color: #111827;
    font-size: 12px;
    min-height: 22px;
    padding: 1px 8px;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    color: #172033;
    min-height: 32px;
    padding: 0 8px;
    font-family: "PingFang SC", "Arial";
}

QLineEdit#stock_search_input {
    min-height: 32px;
    max-height: 32px;
    padding: 0 8px;
    font-family: "PingFang SC", "Arial";
}

QLineEdit#stock_search_input,
QPushButton#add_stock_button,
QPushButton#undo_delete_button,
QPushButton#locate_unconfirmed_button,
QPushButton#check_export_button,
QPushButton#export_button,
QPushButton#more_actions_button {
    min-height: 32px;
    max-height: 32px;
    padding: 0 8px;
}

QComboBox QAbstractItemView,
QListWidget#stock_candidate_popup {
    background: #ffffff;
    border: 1px solid #cfd6e3;
    selection-background-color: #eaf3ff;
    selection-color: #172033;
}

QComboBox QAbstractItemView::item,
QListWidget#stock_candidate_popup::item {
    min-height: 28px;
    padding: 4px 8px;
}

QComboBox QAbstractItemView::item:hover,
QListWidget#stock_candidate_popup::item:hover {
    background: #f3f8ff;
    color: #172033;
}

QPushButton[role="filter_tab"] {
    background: #eef2f7;
    border: 1px solid #d2d9e5;
    border-radius: 6px;
    color: #667085;
    min-height: 30px;
    min-width: 0;
    max-width: 72px;
    padding: 5px 9px;
}

QPushButton[role="filter_tab"]:checked {
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
QLabel#pending_order_badge {
    border-radius: 6px;
    font-size: 12px;
    font-weight: 800;
    padding: 3px 8px;
}

QLabel#stock_type_badge[kind="holding"] {
    background: #fff1f2;
    border: 1px solid #fecdd3;
    color: #be123c;
}

QLabel#stock_type_badge[kind="opening"] {
    background: #eff6ff;
    color: #1d4ed8;
}

QWidget#stock_daily_quote {
    max-height: 24px;
}

QLabel#stock_daily_price,
QLabel#stock_daily_amount {
    color: #172033;
    font-size: 12px;
    font-weight: 800;
}

QLabel#stock_daily_pct {
    font-size: 12px;
    font-weight: 800;
}

QLabel#stock_daily_pct[tone="up"] {
    color: #d40000;
}

QLabel#stock_daily_pct[tone="down"] {
    color: #008f39;
}

QLabel#stock_daily_pct[tone="flat"] {
    color: #172033;
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
    margin-top: 7px;
    padding: 4px;
}

QLabel[side="buy"] {
    color: #2563eb;
    font-weight: 800;
}

QLabel[side="sell_profit"] {
    color: #d40000;
    font-weight: 800;
}

QLabel[side="sell_loss"] {
    color: #008f39;
    font-weight: 800;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QWidget#order_group_header,
QWidget#order_group_title_wrap {
    background: #fbfcfe;
}

QGroupBox[side="buy"] {
    border-top: 3px solid #2563eb;
}

QGroupBox[side="sell_profit"] {
    border-color: #ffb3b3;
    border-top: 3px solid #d40000;
}

QGroupBox[side="sell_loss"] {
    border-color: #80d9a4;
    border-top: 3px solid #008f39;
}

QWidget#order_row {
    background: #ffffff;
    border-left: 4px solid #94a3b8;
}

QWidget#order_row[side="buy"] {
    border-left: 4px solid #2563eb;
}

QWidget#order_row[side="sell_profit"] {
    border-left: 4px solid #d40000;
}

QWidget#order_row[side="sell_loss"] {
    border-left: 4px solid #008f39;
}

QComboBox#order_type_combo {
    font-weight: 700;
}

QComboBox#order_type_combo[side="buy"] {
    color: #2563eb;
}

QComboBox#order_type_combo[side="sell_profit"] {
    color: #d40000;
}

QComboBox#order_type_combo[side="sell_loss"] {
    color: #008f39;
}

QLabel#order_status_indicator {
    border-radius: 3px;
}

QLabel#order_status_indicator[status="pending"] {
    background: #fff7ed;
    border: 1px solid #fed7aa;
}

QLabel#order_status_indicator[status="inherited"] {
    background: #2563eb;
}

QLabel#order_status_indicator[status="confirmed"] {
    background: #ecfdf3;
    border: 1px solid #bbf7d0;
}

QPushButton#order_confirm_button[status="pending"],
QPushButton#order_confirm_button[status="inherited"] {
    background: #172033;
    border-color: #172033;
    color: #ffffff;
    font-weight: 800;
}

QPushButton#order_confirm_button[status="pending"]:hover,
QPushButton#order_confirm_button[status="inherited"]:hover {
    background: #26344d;
    border-color: #26344d;
}

QPushButton#order_confirm_button[status="confirmed"] {
    background: #ecfdf3;
    border-color: #bbf7d0;
    color: #047857;
    font-weight: 800;
}

QPushButton#order_confirm_button[status="confirmed"]:hover {
    background: #dcfce7;
    border-color: #86efac;
}

QPushButton#order_delete_button {
    color: #111827;
}

QPushButton#order_confirm_button,
QPushButton#order_delete_button {
    font-size: 11px;
    min-height: 24px;
    padding: 1px 4px;
}

QPushButton[role="add_order"] {
    background: #ffffff;
    border: 1px solid #b8c2d1;
    border-radius: 4px;
    color: #111827;
    font-size: 13px;
    font-weight: 800;
    min-height: 18px;
    max-height: 18px;
    min-width: 18px;
    max-width: 18px;
    padding: 1px;
}

QPushButton[role="add_order"]:hover {
    background: #eff6ff;
    border-color: #60a5fa;
    color: #0f172a;
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

QPushButton#digit_button[digitCursor="true"] {
    background: #eff6ff;
    border: 2px solid #172033;
}

QPushButton#digit_button:disabled {
    background: #f8fafc;
    border-color: #e5e7eb;
    color: #9ca3af;
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
    if isinstance(app, QApplication):
        families = set(QFontDatabase.families())
        family = "PingFang SC" if "PingFang SC" in families else "Arial"
        app.setFont(QFont(family, 13))
    app.setStyleSheet(APP_STYLESHEET)
