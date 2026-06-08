from __future__ import annotations

from typing import Any

from .core import AuthEntry, build_codex_usage_payload
from .http_client import JsonHttpClient


class CPAClient:
    def __init__(
        self,
        base_url: str,
        management_key: str,
        *,
        http: JsonHttpClient | None = None,
        codex_user_agent: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.management_key = management_key
        self.http = http or JsonHttpClient()
        self.codex_user_agent = codex_user_agent

    def list_auth_files(self) -> Any:
        return self.http.get_json(
            f"{self.base_url}/v0/management/auth-files",
            headers=self._management_headers(),
        )

    def get_codex_usage(self, auth: AuthEntry) -> Any:
        kwargs = {}
        if self.codex_user_agent:
            kwargs["user_agent"] = self.codex_user_agent
        return self.http.post_json(
            f"{self.base_url}/v0/management/api-call",
            build_codex_usage_payload(auth, **kwargs),
            headers=self._management_headers(),
        )

    def _management_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.management_key}"}
