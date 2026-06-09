from ptrade_order_tool.config import AppConfig, load_config, save_config


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

