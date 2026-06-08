from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


DEFAULT_ENV_FILE = "/etc/cpa-codex-quota-bot.env"
ENV_TEMPLATE = """# CPA Codex Quota Telegram Bot
# Fill these values, then run: systemctl restart cpa-codex-quota-bot

TELEGRAM_BOT_TOKEN=replace-with-your-telegram-bot-token
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_OWNER_USER_IDS=replace-with-your-telegram-user-id
TELEGRAM_LEAVE_UNAUTHORIZED_CHATS=true
TELEGRAM_QUOTA_COOLDOWN_SECONDS=10

CPA_BASE_URL=http://127.0.0.1:8317
CPA_MANAGEMENT_KEY=replace-with-your-cpa-management-key
CPA_QUOTA_STATE_FILE=/var/lib/cpa-codex-quota-bot/state.json

# Optional. Keep the default unless the upstream Codex usage endpoint changes
# behavior for older clients.
# CODEX_USER_AGENT=codex_cli_rs/0.76.0

# Optional. Telegram long-poll timeout in seconds.
# TELEGRAM_POLL_TIMEOUT=50
"""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    cpa_base_url: str
    cpa_management_key: str
    allowed_chat_ids: set[int]
    allowed_user_ids: set[int] = field(default_factory=set)
    owner_user_ids: set[int] = field(default_factory=set)
    leave_unauthorized_chats: bool = True
    quota_cooldown_seconds: int = 10
    state_file: str = "/var/lib/cpa-codex-quota-bot/state.json"
    codex_user_agent: str | None = None
    poll_timeout: int = 50


def load_config(env: dict[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    if env is None:
        ensure_env_template(source.get("CPA_QUOTA_ENV_FILE", DEFAULT_ENV_FILE))
    token = _required(source, "TELEGRAM_BOT_TOKEN")
    cpa_key = _required(source, "CPA_MANAGEMENT_KEY")
    return Config(
        telegram_bot_token=token,
        cpa_base_url=source.get("CPA_BASE_URL", "http://127.0.0.1:8317"),
        cpa_management_key=cpa_key,
        allowed_chat_ids=_parse_chat_ids(source.get("TELEGRAM_ALLOWED_CHAT_IDS", "")),
        allowed_user_ids=_parse_chat_ids(source.get("TELEGRAM_ALLOWED_USER_IDS", "")),
        owner_user_ids=_parse_chat_ids(source.get("TELEGRAM_OWNER_USER_IDS", "")),
        leave_unauthorized_chats=_parse_bool(
            source.get("TELEGRAM_LEAVE_UNAUTHORIZED_CHATS", "true")
        ),
        quota_cooldown_seconds=int(source.get("TELEGRAM_QUOTA_COOLDOWN_SECONDS", "10")),
        state_file=source.get(
            "CPA_QUOTA_STATE_FILE",
            "/var/lib/cpa-codex-quota-bot/state.json",
        ),
        codex_user_agent=source.get("CODEX_USER_AGENT") or None,
        poll_timeout=int(source.get("TELEGRAM_POLL_TIMEOUT", "50")),
    )


def _required(source: dict[str, str], key: str) -> str:
    value = source.get(key)
    if not value:
        env_file = source.get("CPA_QUOTA_ENV_FILE", DEFAULT_ENV_FILE)
        ensure_env_template(env_file)
        raise RuntimeError(
            f"missing required environment variable: {key}. "
            f"Edit {env_file}, then restart cpa-codex-quota-bot."
        )
    return value


def ensure_env_template(path: str = DEFAULT_ENV_FILE) -> bool:
    env_path = Path(path)
    if env_path.exists():
        return False
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
        env_path.chmod(0o600)
    except OSError:
        return False
    return True


def _parse_chat_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for item in raw.replace(" ", "").split(","):
        if not item:
            continue
        ids.add(int(item))
    return ids


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() not in {"0", "false", "no", "off"}
