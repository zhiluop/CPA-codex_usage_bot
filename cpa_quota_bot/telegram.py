from __future__ import annotations

from typing import Any

from .http_client import JsonHttpClient


class TelegramClient:
    def __init__(self, token: str, *, http: JsonHttpClient | None = None) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.http = http or JsonHttpClient(timeout=65.0)

    def get_updates(self, *, offset: int | None, timeout: int = 50) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        response = self.http.post_json(f"{self.base_url}/getUpdates", payload)
        if not response.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {response}")
        result = response.get("result", [])
        if not isinstance(result, list):
            raise RuntimeError("Telegram getUpdates returned an invalid result")
        return result

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = self.http.post_json(f"{self.base_url}/sendMessage", payload)
        if not response.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {response}")

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = self.http.post_json(f"{self.base_url}/answerCallbackQuery", payload)
        if not response.get("ok"):
            raise RuntimeError(f"Telegram answerCallbackQuery failed: {response}")

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = self.http.post_json(f"{self.base_url}/editMessageText", payload)
        if not response.get("ok"):
            raise RuntimeError(f"Telegram editMessageText failed: {response}")

    def leave_chat(self, chat_id: int) -> None:
        response = self.http.post_json(
            f"{self.base_url}/leaveChat",
            {"chat_id": chat_id},
        )
        if not response.get("ok"):
            raise RuntimeError(f"Telegram leaveChat failed: {response}")
