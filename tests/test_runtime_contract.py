import json
from decimal import Decimal
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

from ptrade_order_tool.data.db import initialize_schema
from ptrade_order_tool.data.draft_store import DraftStore
from ptrade_order_tool.data.order_exporter import ORDER_TYPES, export_order_json
from ptrade_order_tool.data.ptrade_importer import parse_ptrade_json
from tests.test_ptrade_importer import FakeStockMatcher

RUNTIME_PATH = Path(__file__).parents[1] / "src" / "ptrade_order_tool" / "runtime" / "in-app.py"
PTRADER_FIXTURE = Path(__file__).parent / "fixtures" / "ptrade_20260225.json"


def test_ptrade_runtime_reads_all_exported_order_types():
    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")

    for order_type in ORDER_TYPES:
        assert f'info_dict.get("{order_type}"' in runtime_source


def test_exported_order_json_matches_ptrade_runtime_contract(sqlite_conn, tmp_path):
    initialize_schema(sqlite_conn)
    store = DraftStore(sqlite_conn)
    imported = parse_ptrade_json(PTRADER_FIXTURE, FakeStockMatcher())
    draft = store.create_draft(
        imported,
        expected_trade_date="20260226",
        ptrade_json_path=str(PTRADER_FIXTURE),
        export_json_path=str(tmp_path / "20260225.json"),
    )
    buy_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "buy_limit", Decimal("5"), 1000)
    profit_id = store.add_order(draft.manage_date, "002153.SZ", "石基信息", "sell_profit", Decimal("12.65"), 1000)
    store.confirm_order(buy_id)
    store.confirm_order(profit_id)

    output_path = tmp_path / "20260225.json"
    export_order_json(store.load_draft(draft.manage_date), output_path)
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    order = exported["002153.SZ"]["buy_limit"][0]

    assert set(exported["002153.SZ"]) == {"stock_name", "buy_limit", "sell_profit"}
    assert isinstance(exported["002153.SZ"]["stock_name"], str)
    assert isinstance(order["price"], int | float)
    assert not isinstance(order["price"], str)
    assert isinstance(order["shares"], int)
    assert order == {"price": 5, "shares": 1000}


def test_ptrade_runtime_keeps_previous_monitoring_data_when_new_json_fails(tmp_path):
    runtime = run_path(str(RUNTIME_PATH))
    g = SimpleNamespace(
        account="test",
        entrust_record={"buy": {"old": object()}},
        order_data_ready=True,
        order_dir="order_data/",
        order_result={"000001.SZ": {"stock_name": "旧监控", "buy_limit": [{"price": 1.0, "shares": 1000}]}},
        notebook_path=str(tmp_path) + "/",
    )
    before_trading_start = runtime["before_trading_start"]
    runtime_globals = before_trading_start.__globals__
    runtime_globals["g"] = g
    runtime_globals["log"] = SimpleNamespace(warning=lambda *args, **kwargs: None, info=lambda *args, **kwargs: None)
    runtime_globals["permission_test"] = lambda **kwargs: True
    runtime_globals["date_str_to_weekday"] = lambda value: "周一"

    def fake_trading_day(date, day):
        return "20260226" if day == 1 else "20260225"

    runtime_globals["get_trading_day_by_date"] = fake_trading_day
    runtime_globals["read_json"] = lambda path: (_ for _ in ()).throw(FileNotFoundError(path))

    before_trading_start(SimpleNamespace(), None)

    assert g.entrust_record == {}
    assert g.order_data_ready is True
    assert g.order_result == {"000001.SZ": {"stock_name": "旧监控", "buy_limit": [{"price": 1.0, "shares": 1000}]}}


def test_ptrade_runtime_replaces_previous_monitoring_data_when_new_json_is_valid(tmp_path):
    runtime = run_path(str(RUNTIME_PATH))
    g = SimpleNamespace(
        account="test",
        entrust_record={},
        order_data_ready=True,
        order_dir="order_data/",
        order_result={"000001.SZ": {"stock_name": "旧监控", "buy_limit": [{"price": 1.0, "shares": 1000}]}},
        notebook_path=str(tmp_path) + "/",
    )
    before_trading_start = runtime["before_trading_start"]
    runtime_globals = before_trading_start.__globals__
    runtime_globals["g"] = g
    runtime_globals["log"] = SimpleNamespace(warning=lambda *args, **kwargs: None, info=lambda *args, **kwargs: None)
    runtime_globals["permission_test"] = lambda **kwargs: True
    runtime_globals["date_str_to_weekday"] = lambda value: "周一"
    runtime_globals["get_trading_day_by_date"] = lambda date, day: "20260226" if day == 1 else "20260225"
    runtime_globals["read_json"] = lambda path: {
        "002153.SZ": {
            "stock_name": "石基信息",
            "buy_limit": [{"price": 5, "shares": 1000}],
        }
    }

    before_trading_start(SimpleNamespace(), None)

    assert g.order_data_ready is True
    assert g.order_result == {"002153.SZ": {"stock_name": "石基信息", "buy_limit": [{"price": 5, "shares": 1000}]}}
