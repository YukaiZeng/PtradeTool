from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ptrade_order_tool.bootstrap import create_app_service
from ptrade_order_tool.config import get_executable_dir, get_user_data_dir
from ptrade_order_tool.data.stock_master import MissingTushareToken
from ptrade_order_tool.data.tushare_client import TushareProClient
from ptrade_order_tool.ui.main_window import MainWindow
from ptrade_order_tool.ui.styles import apply_app_style


class TradeCalendarMaintenanceWorker(QThread):
    finishedWithRows = Signal(list)

    def __init__(self, token: str, start_date: str, end_date: str) -> None:
        super().__init__()
        self.token = token
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        try:
            rows = TushareProClient(self.token, timeout=5).query(
                "trade_cal",
                start_date=self.start_date,
                end_date=self.end_date,
                fields="cal_date,is_open",
            )
        except Exception:
            return
        if not self.isInterruptionRequested():
            self.finishedWithRows.emit(rows)


def main() -> int:
    app = QApplication(sys.argv)
    apply_app_style(app)
    service = create_app_service()
    startup = service.open_latest_on_startup()
    window = MainWindow(startup.draft, service, auto_update_daily_quotes=True)
    window.set_startup_message(startup.message)
    window.show()
    QTimer.singleShot(0, lambda: start_trade_calendar_maintenance(service, window))
    return app.exec()


def start_trade_calendar_maintenance(service, owner=None) -> TradeCalendarMaintenanceWorker | None:
    if not hasattr(service, "stock_update_fetch_plan") or not hasattr(service, "calendar"):
        return None
    today = datetime.now().strftime("%Y%m%d")
    try:
        plan = service.stock_update_fetch_plan(
            today=today,
            executable_dir=get_executable_dir(),
            user_data_dir=get_user_data_dir(),
        )
    except MissingTushareToken:
        return None
    except Exception:
        return None

    worker = TradeCalendarMaintenanceWorker(
        plan["token"],
        plan["calendar_start_date"],
        plan["calendar_end_date"],
    )

    def apply_rows(rows: list[dict[str, object]]) -> None:
        if worker.isInterruptionRequested():
            return
        try:
            service.calendar.upsert_trade_calendar(rows, updated_on=today)
        except Exception:
            return

    def cleanup() -> None:
        if owner is not None and hasattr(owner, "_background_workers"):
            owner._background_workers.discard(worker)
        if owner is not None and getattr(owner, "_startup_trade_calendar_worker", None) is worker:
            setattr(owner, "_startup_trade_calendar_worker", None)
        worker.deleteLater()

    worker.finishedWithRows.connect(apply_rows)
    worker.finished.connect(cleanup)
    if owner is not None:
        setattr(owner, "_startup_trade_calendar_worker", worker)
        if hasattr(owner, "_track_background_worker"):
            owner._track_background_worker(worker)
    worker.start()
    return worker


if __name__ == "__main__":
    raise SystemExit(main())
