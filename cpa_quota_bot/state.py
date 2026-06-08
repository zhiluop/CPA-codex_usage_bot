from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RuntimeStateStore:
    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None
        self.allowed_chat_ids: set[int] = set()
        self.allowed_user_ids: set[int] = set()
        self._load()

    def add_allowed_chat(self, chat_id: int) -> None:
        self.allowed_chat_ids.add(chat_id)
        self._save()

    def add_allowed_user(self, user_id: int) -> None:
        self.allowed_user_ids.add(user_id)
        self._save()

    def snapshot(self) -> dict[str, list[int]]:
        return {
            "allowed_chat_ids": sorted(self.allowed_chat_ids),
            "allowed_user_ids": sorted(self.allowed_user_ids),
        }

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.allowed_chat_ids = _parse_ids(raw.get("allowed_chat_ids"))
        self.allowed_user_ids = _parse_ids(raw.get("allowed_user_ids"))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _parse_ids(value: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(value, list):
        return ids
    for item in value:
        try:
            ids.add(int(item))
        except (TypeError, ValueError):
            continue
    return ids
