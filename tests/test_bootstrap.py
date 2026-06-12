from ptrade_order_tool.bootstrap import create_app_service
from ptrade_order_tool.config import AppConfig, save_config


def test_create_app_service_initializes_database(tmp_path):
    save_config(AppConfig(), tmp_path)

    service = create_app_service(tmp_path)

    assert (tmp_path / "app.db").exists()
    startup = service.open_latest_on_startup()
    assert startup.draft is not None
    assert startup.draft.ptrade_json_path == ""
    assert "空白交易单" in startup.message


def test_create_app_service_configures_rotating_log(tmp_path):
    save_config(AppConfig(), tmp_path)

    service = create_app_service(tmp_path)
    service.open_latest_on_startup()

    log_text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "startup_open_latest missing" in log_text
