from __future__ import annotations

import json
import re
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


TELEGRAM_TOKEN_IN_URL = re.compile(r"(https://api\.telegram\.org/bot)[^/]+")


class JsonHttpClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return self.request_json("GET", url, headers=headers)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        return self.request_json("POST", url, body=body, headers=request_headers)

    def request_json(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        req = request.Request(url, data=body, headers=headers or {}, method=method)
        safe_url = _redact_url(url)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {safe_url} failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {safe_url} failed: {exc.reason}") from exc

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {safe_url} did not return JSON") from exc


def _redact_url(url: str) -> str:
    return TELEGRAM_TOKEN_IN_URL.sub(r"\1<redacted>", url)
