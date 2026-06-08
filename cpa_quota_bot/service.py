from __future__ import annotations

from typing import Any

from .core import filter_codex_auths, parse_codex_usage


class QuotaService:
    def __init__(self, cpa_client: Any) -> None:
        self.cpa_client = cpa_client

    def get_reports(self) -> list[dict[str, Any]]:
        auths = filter_codex_auths(self.cpa_client.list_auth_files())
        reports: list[dict[str, Any]] = []
        for auth in auths:
            reports.append(
                {
                    "auth": auth,
                    "windows": parse_codex_usage(self.cpa_client.get_codex_usage(auth)),
                }
            )
        return reports
