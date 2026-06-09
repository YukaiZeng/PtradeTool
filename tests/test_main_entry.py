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
    def open_latest_on_startup(self):
        return FakeStartup()


class FakeWindow:
    instance = None

    def __init__(self, draft, service, **kwargs):
        FakeWindow.instance = self
        self.draft = draft
        self.service = service
        self.kwargs = kwargs
        self.message = ""
        self.shown = False

    def set_startup_message(self, message):
        self.message = message

    def show(self):
        self.shown = True


def test_main_injects_service_into_main_window(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(main_module, "QApplication", FakeApp)
    monkeypatch.setattr(main_module, "create_app_service", lambda: service)
    monkeypatch.setattr(main_module, "MainWindow", FakeWindow)
    monkeypatch.setattr(main_module.sys, "argv", ["ptrade-order-tool"])

    exit_code = main_module.main()

    assert exit_code == 0
    assert FakeWindow.instance.service is service
    assert FakeWindow.instance.message == "ok"
    assert FakeWindow.instance.shown is True
