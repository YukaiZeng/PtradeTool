from pathlib import Path

from ptrade_order_tool import config as config_module
from ptrade_order_tool.config import AppConfig, get_executable_dir, load_config, save_config


def test_missing_config_returns_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config == AppConfig()


def test_config_round_trip(tmp_path):
    original = AppConfig(
        ptrade_data_dir="/tmp/ptrade_data",
        order_data_dir="/tmp/order_data",
        last_opened_manage_date="20260225",
        window_geometry="abc",
    )

    save_config(original, tmp_path)
    loaded = load_config(tmp_path)

    assert loaded == original


def test_get_executable_dir_uses_packaged_executable_parent(monkeypatch):
    executable = Path("dist") / "PtradeOrderTool" / "PtradeOrderTool.exe"
    monkeypatch.setattr(config_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config_module.sys, "executable", str(executable))

    assert get_executable_dir() == executable.resolve().parent
