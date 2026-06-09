from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ptrade_order_tool.bootstrap import create_app_service
from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.styles import apply_app_style


def main() -> int:
    app = QApplication(sys.argv)
    apply_app_style(app)
    service = create_app_service()
    startup = service.open_latest_on_startup()
    window = MainWindow(startup.draft, service)
    window.set_startup_message(startup.message)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
