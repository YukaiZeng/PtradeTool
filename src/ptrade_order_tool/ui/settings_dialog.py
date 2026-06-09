from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ptrade_order_tool.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None, *, token_hint: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ptrade_data_dir_input = QLineEdit(config.ptrade_data_dir)
        self.ptrade_data_dir_input.setObjectName("ptrade_data_dir_input")
        self.order_data_dir_input = QLineEdit(config.order_data_dir)
        self.order_data_dir_input.setObjectName("order_data_dir_input")
        self.tushare_token_input = QLineEdit()
        self.tushare_token_input.setObjectName("tushare_token_input")
        self.tushare_token_input.setEchoMode(QLineEdit.Password)
        self.tushare_token_input.setPlaceholderText(token_hint or "留空表示不修改 TUSHARE_TOKEN")

        form.addRow("Ptrade 盘后目录", self._make_directory_row(self.ptrade_data_dir_input))
        form.addRow("订单导出目录", self._make_directory_row(self.order_data_dir_input))
        form.addRow("Tushare Token", self.tushare_token_input)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _make_directory_row(self, input_widget: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        browse_button = QPushButton("浏览")
        browse_button.setObjectName(f"{input_widget.objectName()}_browse")
        browse_button.clicked.connect(lambda: self._browse_directory(input_widget))
        layout.addWidget(input_widget)
        layout.addWidget(browse_button)
        return row

    def _browse_directory(self, input_widget: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择数据目录", input_widget.text().strip())
        if directory:
            input_widget.setText(directory)

    def to_config(self, base_config: AppConfig) -> AppConfig:
        return AppConfig(
            ptrade_data_dir=self.ptrade_data_dir_input.text().strip(),
            order_data_dir=self.order_data_dir_input.text().strip(),
            last_opened_manage_date=base_config.last_opened_manage_date,
            window_geometry=base_config.window_geometry,
        )

    def token_text(self) -> str:
        return self.tushare_token_input.text().strip()
