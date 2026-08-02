from ptrade_order_tool.data.daily_quote_store import DAILY_FIELDS
from ptrade_order_tool.ui.main_window import DailyQuotesWorker


def test_daily_quotes_worker_emits_only_requested_stocks(monkeypatch):
    calls = []

    def query(_self, api_name, **kwargs):
        calls.append((api_name, kwargs))
        return [
            {"ts_code": "600000.SH", "trade_date": "20260225"},
            {"ts_code": "000001.SZ", "trade_date": "20260225"},
        ]

    monkeypatch.setattr(
        "ptrade_order_tool.ui.main_window.TushareProClient.query",
        query,
    )
    worker = DailyQuotesWorker("20260225", "token", ["600000.SH"])
    captured = []
    worker.finishedWithRows.connect(lambda manage_date, rows: captured.append((manage_date, rows)))

    worker.run()

    assert captured == [("20260225", [{"ts_code": "600000.SH", "trade_date": "20260225"}])]
    assert calls == [("daily", {"ts_code": "600000.SH", "trade_date": "20260225", "fields": DAILY_FIELDS})]


def test_daily_quotes_worker_deduplicates_requested_codes(monkeypatch):
    calls = []

    def query(_self, api_name, **kwargs):
        calls.append((api_name, kwargs))
        return [{"ts_code": kwargs["ts_code"], "trade_date": kwargs["trade_date"]}]

    monkeypatch.setattr("ptrade_order_tool.ui.main_window.TushareProClient.query", query)
    worker = DailyQuotesWorker("20260225", "token", ["600000.SH", "600000.SH", "000001.SZ"])
    captured = []
    worker.finishedWithRows.connect(lambda manage_date, rows: captured.append((manage_date, rows)))

    worker.run()

    assert calls == [
        ("daily", {"ts_code": "600000.SH", "trade_date": "20260225", "fields": DAILY_FIELDS}),
        ("daily", {"ts_code": "000001.SZ", "trade_date": "20260225", "fields": DAILY_FIELDS}),
    ]
    assert captured == [("20260225", [
        {"ts_code": "600000.SH", "trade_date": "20260225"},
        {"ts_code": "000001.SZ", "trade_date": "20260225"},
    ])]
