from __future__ import annotations

import logging
import math
import time
from typing import Any

from .config import Config
from .core import format_error_message, format_quota_message, is_chat_allowed
from .state import RuntimeStateStore


HELP_TEXT = "\n".join(
    [
        "可用命令:",
        "/quota - 查看 Codex 5h / 1w 剩余额度",
        "/id - 查看当前 chat/user id",
        "/admin - 主人私聊管理面板",
        "/start - 帮助",
        "/help - 帮助",
    ]
)

PRIVATE_COMMANDS = [
    {"command": "quota", "description": "查看 Codex 5h / 1w 剩余额度"},
    {"command": "id", "description": "查看当前 chat/user id"},
    {"command": "start", "description": "查看帮助"},
    {"command": "help", "description": "查看帮助"},
]

OWNER_PRIVATE_COMMANDS = [
    {"command": "quota", "description": "查看 Codex 5h / 1w 剩余额度"},
    {"command": "id", "description": "查看当前 chat/user id"},
    {"command": "admin", "description": "打开主人管理面板"},
    {"command": "allow_chat", "description": "添加群/会话白名单"},
    {"command": "allow_user", "description": "添加用户白名单"},
    {"command": "start", "description": "查看帮助"},
    {"command": "help", "description": "查看帮助"},
]

GROUP_COMMANDS = [
    {"command": "quota", "description": "查看 Codex 5h / 1w 剩余额度"},
]


class QuotaBot:
    def __init__(
        self,
        config: Config,
        telegram: Any,
        quota_service: Any,
        *,
        state_store: RuntimeStateStore | None = None,
        clock: Any = time.time,
    ) -> None:
        self.config = config
        self.telegram = telegram
        self.quota_service = quota_service
        self.state_store = state_store or RuntimeStateStore(config.state_file)
        self.clock = clock
        self.offset: int | None = None
        self.pending_admin_actions: dict[int, str] = {}
        self.last_group_quota_at: dict[int, float] = {}

    def run_forever(self) -> None:
        logging.info("quota bot started")
        self.register_commands()
        while True:
            try:
                self.poll_once()
            except Exception:
                logging.exception("poll failed")
                time.sleep(5)

    def register_commands(self) -> None:
        if not hasattr(self.telegram, "set_my_commands"):
            return
        try:
            self.telegram.set_my_commands(
                PRIVATE_COMMANDS,
                {"type": "all_private_chats"},
            )
            self.telegram.set_my_commands(
                GROUP_COMMANDS,
                {"type": "all_group_chats"},
            )
            for owner_id in sorted(self.config.owner_user_ids):
                self.telegram.set_my_commands(
                    OWNER_PRIVATE_COMMANDS,
                    {"type": "chat", "chat_id": owner_id},
                )
        except Exception:
            logging.warning("failed to register Telegram commands", exc_info=True)

    def poll_once(self) -> None:
        updates = self.telegram.get_updates(
            offset=self.offset,
            timeout=self.config.poll_timeout,
        )
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self.offset = update_id + 1
            self.handle_update(update)

    def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"] or {})
            return

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        chat_type = str(chat.get("type") or "")
        user_id = sender.get("id")
        text = str(message.get("text") or "").strip()
        if not isinstance(chat_id, int) or not text:
            return

        if chat_type == "private" and isinstance(user_id, int):
            if self._handle_pending_admin_text(chat_id, user_id, text):
                return

        command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
        if self._is_group_chat(chat_type) and command != "/quota":
            return

        if command in {"/start", "/help"}:
            self._send_if_allowed(chat_id, user_id, chat_type, HELP_TEXT)
        elif command == "/id":
            self.telegram.send_message(
                chat_id,
                self._format_id_message(chat_id, user_id, chat_type),
            )
        elif command == "/admin":
            self._handle_admin(chat_id, user_id, chat_type)
        elif command in {"/allow_chat", "/allow_user"}:
            self._handle_owner_allow_command(chat_id, user_id, chat_type, text, command)
        elif command == "/quota":
            self._handle_quota(chat_id, user_id, chat_type)

    def _send_if_allowed(
        self,
        chat_id: int,
        user_id: Any,
        chat_type: str,
        text: str,
    ) -> None:
        denial = self._denial_reason(chat_id, user_id)
        if denial:
            self._deny(chat_id, chat_type, denial)
            return
        self.telegram.send_message(chat_id, text)

    def _handle_quota(self, chat_id: int, user_id: Any, chat_type: str) -> None:
        denial = self._denial_reason(chat_id, user_id)
        if denial:
            self._deny(chat_id, chat_type, denial)
            return
        if self._is_group_chat(chat_type):
            retry_after = self._quota_retry_after(chat_id)
            if retry_after is not None:
                self.telegram.send_message(
                    chat_id,
                    f"⏳ 请求太频繁了，请 {retry_after} 秒后再试。",
                )
                return

        try:
            reports = self.quota_service.get_reports()
            if self._is_group_chat(chat_type):
                self.last_group_quota_at[chat_id] = self.clock()
            self.telegram.send_message(chat_id, format_quota_message(reports))
        except Exception as exc:
            logging.exception("quota lookup failed")
            self.telegram.send_message(chat_id, format_error_message(exc))

    def _denial_reason(self, chat_id: int, user_id: Any) -> str | None:
        if not is_chat_allowed(chat_id, self._allowed_chat_ids()):
            return "This chat is not allowed."
        allowed_user_ids = self._allowed_user_ids()
        if allowed_user_ids:
            if not isinstance(user_id, int) or user_id not in allowed_user_ids:
                return "This user is not allowed."
        return None

    def _deny(self, chat_id: int, chat_type: str, reason: str) -> None:
        self.telegram.send_message(chat_id, reason)
        if (
            reason == "This chat is not allowed."
            and self.config.leave_unauthorized_chats
            and chat_type in {"group", "supergroup"}
        ):
            self.telegram.leave_chat(chat_id)

    def _format_id_message(self, chat_id: int, user_id: Any, chat_type: str) -> str:
        user_text = str(user_id) if isinstance(user_id, int) else "unknown"
        return f"chat_id: {chat_id}\nchat_type: {chat_type or 'unknown'}\nuser_id: {user_text}"

    def _handle_admin(self, chat_id: int, user_id: Any, chat_type: str) -> None:
        if not self._is_owner(user_id):
            self.telegram.send_message(chat_id, "Only bot owners can use this command.")
            return
        if chat_type != "private":
            self.telegram.send_message(chat_id, "管理面板只在私聊中可用。")
            return
        self.telegram.send_message(chat_id, self._admin_panel_text(), self._admin_keyboard())

    def _handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        query_id = str(callback_query.get("id") or "")
        sender = callback_query.get("from") or {}
        user_id = sender.get("id")
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        chat_type = str(chat.get("type") or "")
        data = str(callback_query.get("data") or "")
        self.telegram.answer_callback_query(query_id or "unknown")

        if not isinstance(chat_id, int) or chat_type != "private" or not self._is_owner(user_id):
            return

        if data == "admin:add_chat":
            self.pending_admin_actions[int(user_id)] = "add_chat"
            self.telegram.send_message(chat_id, "发送要加入白名单的群/会话 chat_id，例如 -1001234567890")
        elif data == "admin:add_user":
            self.pending_admin_actions[int(user_id)] = "add_user"
            self.telegram.send_message(chat_id, "发送要加入白名单的 Telegram user_id，例如 123456789")
        elif data == "admin:list":
            self.telegram.send_message(chat_id, self._admin_panel_text(), self._admin_keyboard())
        elif data == "admin:cancel":
            self.pending_admin_actions.pop(int(user_id), None)
            self.telegram.send_message(chat_id, "已取消。")

    def _handle_pending_admin_text(self, chat_id: int, user_id: int, text: str) -> bool:
        action = self.pending_admin_actions.get(user_id)
        if not action or not self._is_owner(user_id):
            return False
        try:
            value = int(text.strip())
        except ValueError:
            self.telegram.send_message(chat_id, "请输入纯数字 ID。")
            return True

        if action == "add_chat":
            self.state_store.add_allowed_chat(value)
            self.telegram.send_message(chat_id, f"已添加群/会话白名单: {value}")
        elif action == "add_user":
            self.state_store.add_allowed_user(value)
            self.telegram.send_message(chat_id, f"已添加用户白名单: {value}")
        self.pending_admin_actions.pop(user_id, None)
        return True

    def _handle_owner_allow_command(
        self,
        chat_id: int,
        user_id: Any,
        chat_type: str,
        text: str,
        command: str,
    ) -> None:
        if not self._is_owner(user_id):
            self.telegram.send_message(chat_id, "Only bot owners can use this command.")
            return
        if chat_type != "private":
            self.telegram.send_message(chat_id, "管理命令只在私聊中可用。")
            return
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            self.telegram.send_message(chat_id, f"用法: {command} <id>")
            return
        try:
            value = int(parts[1].strip())
        except ValueError:
            self.telegram.send_message(chat_id, "请输入纯数字 ID。")
            return
        if command == "/allow_chat":
            self.state_store.add_allowed_chat(value)
            self.telegram.send_message(chat_id, f"已添加群/会话白名单: {value}")
        else:
            self.state_store.add_allowed_user(value)
            self.telegram.send_message(chat_id, f"已添加用户白名单: {value}")

    def _admin_keyboard(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "➕ 添加群", "callback_data": "admin:add_chat"},
                    {"text": "👤 添加用户", "callback_data": "admin:add_user"},
                ],
                [
                    {"text": "📋 查看白名单", "callback_data": "admin:list"},
                    {"text": "取消", "callback_data": "admin:cancel"},
                ],
            ]
        }

    def _admin_panel_text(self) -> str:
        chats = sorted(self._allowed_chat_ids())
        users = sorted(self._allowed_user_ids())
        chat_text = ", ".join(str(item) for item in chats) or "空"
        user_text = ", ".join(str(item) for item in users) or "空"
        return "\n".join(
            [
                "⚙️ 管理面板",
                f"群/会话白名单: {chat_text}",
                f"用户白名单: {user_text}",
                "群组内仅响应 /quota，并对每个群做频率限制。",
            ]
        )

    def _quota_retry_after(self, chat_id: int) -> int | None:
        cooldown = max(0, self.config.quota_cooldown_seconds)
        if cooldown == 0:
            return None
        last_seen = self.last_group_quota_at.get(chat_id)
        if last_seen is None:
            return None
        elapsed = self.clock() - last_seen
        if elapsed >= cooldown:
            return None
        return max(1, math.ceil(cooldown - elapsed))

    def _allowed_chat_ids(self) -> set[int]:
        return set(self.config.allowed_chat_ids) | set(self.state_store.allowed_chat_ids)

    def _allowed_user_ids(self) -> set[int]:
        return (
            set(self.config.allowed_user_ids)
            | set(self.state_store.allowed_user_ids)
            | set(self.config.owner_user_ids)
        )

    def _is_owner(self, user_id: Any) -> bool:
        return isinstance(user_id, int) and user_id in self.config.owner_user_ids

    def _is_group_chat(self, chat_type: str) -> bool:
        return chat_type in {"group", "supergroup"}
