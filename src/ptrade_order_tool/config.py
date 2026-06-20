from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


APP_DIR_NAME = "PtradeOrderTool"


@dataclass(slots=True)
class AppConfig:
    ptrade_data_dir: str = ""
    order_data_dir: str = ""
    last_opened_manage_date: str = ""
    window_geometry: str = ""


def get_user_data_dir() -> Path:
    override = os.environ.get("PTRADE_ORDER_TOOL_HOME")
    if override:
        return Path(override).expanduser()

    system_name = platform.system()
    if system_name == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if system_name == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
    return Path.home() / ".ptrade_order_tool"


def get_config_path(user_data_dir: Path | None = None) -> Path:
    return (user_data_dir or get_user_data_dir()) / "config.json"


def get_executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def load_config(user_data_dir: Path | None = None) -> AppConfig:
    config_path = get_config_path(user_data_dir)
    if not config_path.exists():
        return AppConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = set(AppConfig.__dataclass_fields__)
    return AppConfig(**{key: value for key, value in data.items() if key in allowed})


def save_config(config: AppConfig, user_data_dir: Path | None = None) -> Path:
    config_path = get_config_path(user_data_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path
