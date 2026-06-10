import warnings

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.stock_master import (
    MissingTushareToken,
    StockMaster,
    load_tushare_token,
    save_tushare_token,
)


STOCK_ROWS = [
    {"ts_code": "002153.SZ", "symbol": "002153", "name": "石基信息", "list_status": "L"},
    {"ts_code": "300162.SZ", "symbol": "300162", "name": "雷曼光电", "list_status": "L"},
    {"ts_code": "300251.SZ", "symbol": "300251", "name": "光线传媒", "list_status": "L"},
    {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "list_status": "D"},
]


def make_master(sqlite_conn):
    initialize_schema(sqlite_conn)
    master = StockMaster(sqlite_conn)
    master.upsert_stock_basic(STOCK_ROWS, updated_on="20260609")
    return master


def test_resolve_stock_by_symbol_and_ts_code(sqlite_conn):
    master = make_master(sqlite_conn)

    assert master.resolve_stock("002153")["name"] == "石基信息"
    assert master.resolve_stock("002153.SZ")["name"] == "石基信息"
    assert master.resolve_stock("131990") is None


def test_search_stocks_by_name_pinyin_and_initials(sqlite_conn):
    master = make_master(sqlite_conn)

    assert master.search_stocks("石基")[0]["ts_code"] == "002153.SZ"
    assert master.search_stocks("shijixinxi")[0]["ts_code"] == "002153.SZ"
    assert master.search_stocks("sjxx")[0]["ts_code"] == "002153.SZ"


def test_upsert_stock_basic_suppresses_pypinyin_deprecation_warning(sqlite_conn):
    initialize_schema(sqlite_conn)
    master = StockMaster(sqlite_conn)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        master.upsert_stock_basic(STOCK_ROWS, updated_on="20260609")

    assert not any("codecs.open" in str(warning.message) for warning in caught)


def test_search_excludes_delisted_stocks(sqlite_conn):
    master = make_master(sqlite_conn)

    assert master.search_stocks("平安银行") == []


def test_update_button_state(sqlite_conn):
    initialize_schema(sqlite_conn)
    master = StockMaster(sqlite_conn)

    assert master.update_button_state("20260609", is_trade_day=False) == "generate"
    master.upsert_stock_basic(STOCK_ROWS, updated_on="20260609")
    assert master.update_button_state("20260609", is_trade_day=True) == "updated_disabled"
    assert master.update_button_state("20260610", is_trade_day=True) == "update_enabled"
    assert master.update_button_state("20260610", is_trade_day=False) == "update_disabled_non_trade_day"


def test_sync_from_tushare_uses_query_result(sqlite_conn):
    initialize_schema(sqlite_conn)
    master = StockMaster(sqlite_conn)

    class FakePro:
        def query(self, api_name, fields):
            assert api_name == "stock_basic"
            assert fields == "ts_code,symbol,name,list_status"
            return [
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行", "list_status": "L"}
            ]

    count = master.sync_from_tushare("token", updated_on="20260609", pro_client=FakePro())

    assert count == 1
    assert master.resolve_stock("600000")["name"] == "浦发银行"


def test_load_tushare_token_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / ".env").write_text("TUSHARE_TOKEN=abc123\n", encoding="utf-8")

    assert load_tushare_token(tmp_path / "exe", user_dir) == "abc123"


def test_load_tushare_token_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    try:
        load_tushare_token(tmp_path / "exe", tmp_path / "user")
    except MissingTushareToken as exc:
        assert "TUSHARE_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected MissingTushareToken")


def test_save_tushare_token_creates_and_updates_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    user_dir = tmp_path / "user"

    env_path = save_tushare_token(user_dir, "first-token")
    assert env_path.read_text(encoding="utf-8") == "TUSHARE_TOKEN=first-token\n"
    assert load_tushare_token(tmp_path / "exe", user_dir) == "first-token"

    save_tushare_token(user_dir, "second-token")
    assert env_path.read_text(encoding="utf-8") == "TUSHARE_TOKEN=second-token\n"
    assert load_tushare_token(tmp_path / "exe", user_dir) == "second-token"


def test_save_tushare_token_preserves_other_env_lines(tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / ".env").write_text("OTHER=value\nTUSHARE_TOKEN=old\n", encoding="utf-8")

    save_tushare_token(user_dir, "new")

    assert (user_dir / ".env").read_text(encoding="utf-8") == "OTHER=value\nTUSHARE_TOKEN=new\n"
