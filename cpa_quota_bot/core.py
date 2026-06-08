from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable


CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
DEFAULT_CODEX_USER_AGENT = "codex_cli_rs/0.76.0"


@dataclass(frozen=True)
class AuthEntry:
    name: str
    auth_index: str
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class QuotaWindow:
    label: str
    used_percent: float
    remaining_percent: float
    resets_in: str | None = None


def is_chat_allowed(chat_id: int, allowed_chat_ids: set[int]) -> bool:
    return not allowed_chat_ids or chat_id in allowed_chat_ids


def filter_codex_auths(payload: Any) -> list[AuthEntry]:
    entries = list(_auth_entries_from_payload(payload))
    codex_entries: list[AuthEntry] = []

    for raw in entries:
        provider = str(_first_present(raw, "provider", "type", "api", "source") or "")
        name = str(_first_present(raw, "name", "filename", "file", "path") or "")
        lower_marker = f"{provider} {name}".lower()
        if "codex" not in lower_marker:
            continue
        if _is_disabled(raw):
            continue

        auth_index = _first_present(raw, "auth_index", "authIndex", "index")
        if auth_index is None:
            continue

        codex_entries.append(
            AuthEntry(
                name=name or f"auth-{auth_index}",
                auth_index=str(auth_index),
                account_id=_string_or_none(
                    _first_present(raw, "chatgpt_account_id", "account_id")
                    or _find_key(raw, "chatgpt_account_id")
                    or _find_key(raw, "account_id")
                ),
                email=_string_or_none(
                    _first_present(raw, "email", "account_email")
                    or _find_key(raw, "email")
                ),
                plan_type=_string_or_none(
                    _first_present(raw, "plan_type", "plan")
                    or _find_key(raw, "plan_type")
                    or _find_key(raw, "plan")
                ),
                status=_string_or_none(_first_present(raw, "status", "state")),
            )
        )

    return codex_entries


def build_codex_usage_payload(
    auth: AuthEntry,
    *,
    user_agent: str = DEFAULT_CODEX_USER_AGENT,
) -> dict[str, Any]:
    headers = {
        "Authorization": "Bearer $TOKEN$",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    if auth.account_id:
        headers["Chatgpt-Account-Id"] = auth.account_id

    return {
        "auth_index": auth.auth_index,
        "method": "GET",
        "url": CODEX_USAGE_URL,
        "header": headers,
    }


def parse_codex_usage(response: Any) -> list[QuotaWindow]:
    body = _extract_body(response)
    rate_limit = body.get("rate_limit", {}) if isinstance(body, dict) else {}

    raw_windows = []
    if isinstance(rate_limit, dict):
        for key in ("primary_window", "secondary_window"):
            value = rate_limit.get(key)
            if isinstance(value, dict):
                raw_windows.append(value)
        for value in rate_limit.values():
            if isinstance(value, dict) and value not in raw_windows:
                raw_windows.append(value)

    windows: list[QuotaWindow] = []
    for raw in raw_windows:
        label = _window_label(raw)
        if label is None:
            continue
        used = _float_or_none(raw.get("used_percent"))
        if used is None:
            continue
        used = _clamp_percent(used)
        windows.append(
            QuotaWindow(
                label=label,
                used_percent=used,
                remaining_percent=round(100.0 - used, 1),
                resets_in=None,
            )
        )

    order = {"5h": 0, "1w": 1}
    return sorted(windows, key=lambda item: order.get(item.label, 99))


def format_quota_message(reports: Iterable[dict[str, Any]]) -> str:
    report_list = list(reports)
    count = len(report_list)
    if count == 0:
        return "📊 Codex 用量: 没有找到可用的 Codex 账号。"

    lines = [f"📊 Codex 用量: {count} 个账号"]
    for report in report_list:
        auth = report["auth"]
        windows = report.get("windows") or []
        title = mask_account_name(auth.email or auth.name or f"auth {auth.auth_index}")
        details = []
        if auth.plan_type:
            details.append(f"套餐: {auth.plan_type}")
        if auth.status:
            details.append(f"状态: {auth.status}")

        lines.append("")
        lines.append(f"👤 {title}")
        if details:
            lines.append(f"  {'; '.join(details)}")
        if not windows:
            lines.append("  用量: 暂不可用")
            continue
        for window in windows:
            reset_text = f", resets in {window.resets_in}" if window.resets_in else ""
            icon = "🕔" if window.label == "5h" else "📅"
            level = _quota_level_icon(window.remaining_percent)
            bar = _quota_bar(window.remaining_percent)
            lines.append(
                f"  {icon} {window.label}: {level} {bar} {window.remaining_percent:.1f}% 剩余 "
                f"({window.used_percent:.1f}% 已用{reset_text})"
            )

    return "\n".join(lines)


def format_error_message(error: Exception) -> str:
    return f"⚠️ Codex 用量查询失败: {error}"


def mask_account_name(value: str) -> str:
    if "@" in value:
        local, domain = value.split("@", 1)
        prefix = 2 if len(local) >= 6 else 1
        return f"{_mask_token(local, prefix=prefix, suffix=1)}@{domain}"
    return _mask_token(value, prefix=2, suffix=2)


def _mask_token(value: str, *, prefix: int, suffix: int) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) == 3:
        return f"{value[0]}*{value[-1]}"
    prefix = min(prefix, max(1, len(value) - 2))
    suffix = min(suffix, max(1, len(value) - prefix - 1))
    left = value[:prefix]
    right = value[-suffix:]
    return f"{left}{'*' * max(1, len(value) - prefix - suffix)}{right}"


def _quota_bar(remaining_percent: float, width: int = 10) -> str:
    filled = int(round((remaining_percent / 100.0) * width))
    filled = max(0, min(width, filled))
    if remaining_percent > 0 and filled == 0:
        filled = 1
    if remaining_percent >= 50:
        block = "🟩"
    elif remaining_percent >= 20:
        block = "🟨"
    else:
        block = "🟥"
    return block * filled + "⬜" * (width - filled)


def _quota_level_icon(remaining_percent: float) -> str:
    if remaining_percent >= 50:
        return "🟢"
    if remaining_percent >= 20:
        return "🟡"
    return "🔴"


def _auth_entries_from_payload(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return

    if not isinstance(payload, dict):
        return

    for key in ("files", "auth_files", "authFiles", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
            return


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in ("", None):
            return payload[key]
    return None


def _find_key(value: Any, target: str) -> Any:
    if isinstance(value, dict):
        if target in value and value[target] not in ("", None):
            return value[target]
        for child in value.values():
            found = _find_key(child, target)
            if found not in ("", None):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, target)
            if found not in ("", None):
                return found
    return None


def _is_disabled(raw: dict[str, Any]) -> bool:
    if raw.get("disabled") is True or raw.get("enabled") is False:
        return True
    status = str(_first_present(raw, "status", "state") or "").lower()
    return status in {"disabled", "disable", "inactive", "unavailable", "error"}


def _extract_body(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("CPA api-call response must be a JSON object")

    status_code = int(response.get("status_code") or response.get("status") or 200)
    if status_code >= 400:
        raise ValueError(f"upstream usage request returned HTTP {status_code}")

    body = response.get("body", response)
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("upstream usage response body is not JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("upstream usage response body must be a JSON object")
        return parsed
    if isinstance(body, dict):
        return body
    raise ValueError("upstream usage response body is missing")


def _window_label(window: dict[str, Any]) -> str | None:
    seconds = _float_or_none(window.get("limit_window_seconds") or window.get("seconds"))
    if seconds is None:
        name = str(window.get("name") or window.get("label") or "").lower()
        if "5h" in name or "5 hour" in name:
            return "5h"
        if "1w" in name or "7d" in name or "week" in name:
            return "1w"
        return None

    if int(seconds) == 18000:
        return "5h"
    if int(seconds) == 604800:
        return "1w"
    return None


def _float_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_percent(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 1)


def _string_or_none(value: Any) -> str | None:
    if value in ("", None):
        return None
    return str(value)
