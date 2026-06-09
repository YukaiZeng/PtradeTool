from __future__ import annotations

import json
from urllib import request
from urllib.error import URLError


class TushareProClient:
    def __init__(self, token: str, timeout: int = 30) -> None:
        self.token = token
        self.timeout = timeout
        self.base_url = "http://api.waditu.com/dataapi"

    def query(self, api_name: str, fields: str = "", **kwargs) -> list[dict[str, object]]:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": kwargs,
            "fields": fields,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/{api_name}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except URLError as exc:
            raise RuntimeError(f"Tushare 请求失败: {exc}") from exc

        result = json.loads(body)
        if result.get("code") != 0:
            raise RuntimeError(str(result.get("msg", "Tushare 请求失败")))
        data_block = result.get("data", {})
        columns = data_block.get("fields", [])
        items = data_block.get("items", [])
        return [dict(zip(columns, item)) for item in items]
