import json

import pytest

from ptrade_order_tool.data.tushare_client import TushareProClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_tushare_pro_client_query_converts_rows(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(
            {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "name"],
                    "items": [["600000.SH", "浦发银行"]],
                },
            }
        )

    monkeypatch.setattr("ptrade_order_tool.data.tushare_client.request.urlopen", fake_urlopen)

    rows = TushareProClient("token", timeout=5).query("stock_basic", fields="ts_code,name")

    assert captured["timeout"] == 5
    assert captured["body"]["api_name"] == "stock_basic"
    assert captured["body"]["token"] == "token"
    assert captured["body"]["fields"] == "ts_code,name"
    assert rows == [{"ts_code": "600000.SH", "name": "浦发银行"}]


def test_tushare_pro_client_raises_on_error(monkeypatch):
    monkeypatch.setattr(
        "ptrade_order_tool.data.tushare_client.request.urlopen",
        lambda *args, **kwargs: FakeResponse({"code": -1, "msg": "bad token"}),
    )

    with pytest.raises(RuntimeError, match="bad token"):
        TushareProClient("token").query("stock_basic")


def test_tushare_pro_client_uses_https():
    assert TushareProClient("token").base_url.startswith("https://")
