from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ptrade_order_tool.bootstrap import create_app_service
from ptrade_order_tool.config import get_user_data_dir
from ptrade_order_tool.data.stock_master import MissingTushareToken
from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.styles import apply_app_style


def main() -> int:
    app = QApplication(sys.argv)
    apply_app_style(app)
    service = create_app_service()
    prepare_trade_calendar(service)
    startup = service.open_latest_on_startup()
    window = MainWindow(startup.draft, service, auto_update_daily_quotes=True)
    window.set_startup_message(startup.message)
    window.show()
    return app.exec()


def prepare_trade_calendar(service) -> None:
    if not hasattr(service, "maintain_trade_calendar"):
        return
    try:
        service.maintain_trade_calendar(
            today=datetime.now().strftime("%Y%m%d"),
            executable_dir=Path.cwd(),
            user_data_dir=get_user_data_dir(),
        )
    except MissingTushareToken:
        return
    except Exception:
        return


if __name__ == "__main__":
    raise SystemExit(main())
