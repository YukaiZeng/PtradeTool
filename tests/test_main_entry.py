from ptrade_order_tool import main as main_module


class FakeStartup:
    draft = None
    message = "ok"


class FakeApp:
    instance = None

    def __init__(self, argv):
        FakeApp.instance = self
        self.argv = argv
        self.stylesheet = ""

    def setStyleSheet(self, stylesheet):
        self.stylesheet = stylesheet

    def setFont(self, font):
        self.font = font

    def exec(self):
        return 0


class FakeService:
    def __init__(self):
        self.calls = []
        self.calendar = FakeCalendar()

    def open_latest_on_startup(self):
        self.calls.append(("open_latest_on_startup", {}))
        return FakeStartup()

    def stock_update_fetch_plan(self, **kwargs):
        self.calls.append(("stock_update_fetch_plan", kwargs))
        return {
            "token": "token",
            "today": kwargs["today"],
            "calendar_start_date": "20260101",
            "calendar_end_date": "20271231",
        }


class FakeCalendar:
    def __init__(self):
        self.rows = []

    def upsert_trade_calendar(self, rows, updated_on):
        self.rows.append((rows, updated_on))


class FakeWindow:
    instance = None

    def __init__(self, draft, service, **kwargs):
        FakeWindow.instance = self
        self.draft = draft
        self.service = service
        self.kwargs = kwargs
        self.message = ""
        self.shown = False
        self._background_workers = set()
        self._startup_trade_calendar_worker = None

    def set_startup_message(self, message):
        self.message = message

    def show(self):
        self.shown = True

    def _track_background_worker(self, worker):
        self._background_workers.add(worker)


class FakeTimer:
    callbacks = []

    @staticmethod
    def singleShot(delay, callback):  # noqa: N802
        FakeTimer.callbacks.append((delay, callback))


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class FakeTradeCalendarMaintenanceWorker:
    instances = []

    def __init__(self, token, start_date, end_date):
        self.token = token
        self.start_date = start_date
        self.end_date = end_date
        self.started = False
        self.deleted = False
        self.finishedWithRows = FakeSignal()
        self.finished = FakeSignal()
        FakeTradeCalendarMaintenanceWorker.instances.append(self)

    def isInterruptionRequested(self):
        return False

    def deleteLater(self):
        self.deleted = True

    def start(self):
        self.started = True


class FakeDateTime:
    @staticmethod
    def now():
        return FakeDateTime()

    def strftime(self, fmt):
        return "20260624"


def test_main_injects_service_into_main_window(monkeypatch):
    service = FakeService()
    FakeTimer.callbacks = []
    FakeTradeCalendarMaintenanceWorker.instances = []
    monkeypatch.setattr(main_module, "QApplication", FakeApp)
    monkeypatch.setattr(main_module, "QTimer", FakeTimer)
    monkeypatch.setattr(main_module, "TradeCalendarMaintenanceWorker", FakeTradeCalendarMaintenanceWorker)
    monkeypatch.setattr(main_module, "datetime", FakeDateTime)
    monkeypatch.setattr(main_module, "create_app_service", lambda: service)
    monkeypatch.setattr(main_module, "MainWindow", FakeWindow)
    monkeypatch.setattr(main_module.sys, "argv", ["ptrade-order-tool"])

    exit_code = main_module.main()

    assert exit_code == 0
    assert [name for name, _ in service.calls] == ["open_latest_on_startup"]
    assert FakeWindow.instance.service is service
    assert FakeWindow.instance.message == "ok"
    assert FakeWindow.instance.shown is True
    assert len(FakeTimer.callbacks) == 1
    assert FakeTimer.callbacks[0][0] == 0

    FakeTimer.callbacks[0][1]()

    assert [name for name, _ in service.calls] == ["open_latest_on_startup", "stock_update_fetch_plan"]
    worker = FakeTradeCalendarMaintenanceWorker.instances[0]
    assert worker.started is True
    assert worker.token == "token"
    assert worker.start_date == "20260101"
    assert worker.end_date == "20271231"
    assert FakeWindow.instance._startup_trade_calendar_worker is worker
    assert worker in FakeWindow.instance._background_workers

    worker.finishedWithRows.emit([{"cal_date": "20260624", "is_open": 1}])
    assert service.calendar.rows == [([{"cal_date": "20260624", "is_open": 1}], "20260624")]

    worker.finished.emit()
    assert worker.deleted is True
    assert FakeWindow.instance._startup_trade_calendar_worker is None
    assert worker not in FakeWindow.instance._background_workers
