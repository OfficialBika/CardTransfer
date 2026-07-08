from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable

from pyrogram import Client
from pyrogram.types import Message

from utils.logger import get_logger
from utils.retry import run_with_retries

log = get_logger(__name__)


class PaginationError(RuntimeError):
    pass


class PaginationScanner:
    def __init__(
        self,
        *,
        bot_username: str,
        bot_id: int,
        harem_command: str,
        parser: Callable[[str], list[int]],
        page_timeout: float,
        max_pages: int,
        max_retries: int,
    ) -> None:
        self.bot_username = bot_username.lstrip("@")
        self.bot_id = bot_id
        self.harem_command = harem_command
        self.parser = parser
        self.page_timeout = page_timeout
        self.max_pages = max_pages
        self.max_retries = max_retries

    @property
    def peer(self) -> str:
        return f"@{self.bot_username}"

    async def scan(self, client: Client) -> list[int]:
        await self._warm_peer(client)

        async def send_harem() -> Message:
            return await client.send_message(self.peer, self.harem_command)

        command_message = await run_with_retries(
            send_harem,
            attempts=self.max_retries,
            label=f"send {self.harem_command} to @{self.bot_username}",
        )

        current = await self._wait_for_initial_response(client, command_message.id)
        all_ids: list[int] = []
        seen_ids: set[int] = set()
        seen_pages: set[str] = set()

        for page_number in range(1, self.max_pages + 1):
            text = self._message_text(current)
            fingerprint = self._fingerprint(current, text)
            if fingerprint in seen_pages:
                log.warning(
                    "Repeated page detected for @%s at page %s; stopping pagination",
                    self.bot_username,
                    page_number,
                )
                break
            seen_pages.add(fingerprint)

            page_ids = self.parser(text)
            for item_id in page_ids:
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_ids.append(item_id)

            log.info(
                "@%s page %s scanned: %s ids on page, %s unique total",
                self.bot_username,
                page_number,
                len(page_ids),
                len(all_ids),
            )

            next_button = self._find_next_button(current)
            if next_button is None:
                break

            before = self._snapshot(current)
            await self._click_button(client, current, *next_button)
            current = await self._wait_for_page_change(client, current, before)
        else:
            raise PaginationError(
                f"Reached MAX_PAGES={self.max_pages} while scanning @{self.bot_username}"
            )

        if not all_ids:
            raise PaginationError(
                f"No character IDs were found in @{self.bot_username} /harem pages"
            )
        return all_ids

    async def _warm_peer(self, client: Client) -> None:
        async def resolve() -> object:
            return await client.get_users(self.peer)

        await run_with_retries(
            resolve,
            attempts=self.max_retries,
            label=f"resolve @{self.bot_username}",
        )

    async def _wait_for_initial_response(
        self, client: Client, after_message_id: int
    ) -> Message:
        deadline = time.monotonic() + self.page_timeout
        while time.monotonic() < deadline:
            async for message in client.get_chat_history(self.peer, limit=12):
                if self._is_target_bot_message(message) and message.id > after_message_id:
                    if self._message_text(message) or message.reply_markup:
                        return message
            await asyncio.sleep(0.8)
        raise TimeoutError(
            f"Timed out waiting for @{self.bot_username} to answer {self.harem_command}"
        )

    async def _wait_for_page_change(
        self,
        client: Client,
        previous_message: Message,
        before_snapshot: str,
    ) -> Message:
        deadline = time.monotonic() + self.page_timeout
        while time.monotonic() < deadline:
            refreshed = await client.get_messages(self.peer, previous_message.id)
            if refreshed and self._snapshot(refreshed) != before_snapshot:
                return refreshed

            async for candidate in client.get_chat_history(self.peer, limit=8):
                if not self._is_target_bot_message(candidate):
                    continue
                if candidate.id > previous_message.id:
                    return candidate
            await asyncio.sleep(0.7)
        raise TimeoutError(
            f"Timed out waiting for next page from @{self.bot_username}"
        )

    def _is_target_bot_message(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id == self.bot_id)

    @staticmethod
    def _message_text(message: Message) -> str:
        return message.text or message.caption or ""

    @classmethod
    def _snapshot(cls, message: Message) -> str:
        markup_parts: list[str] = []
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        for row in rows:
            for button in row:
                markup_parts.append(getattr(button, "text", "") or "")
                data = getattr(button, "callback_data", None)
                if data is not None:
                    markup_parts.append(repr(data))
        return "|".join(
            [str(message.id), cls._message_text(message), *markup_parts]
        )

    @classmethod
    def _fingerprint(cls, message: Message, text: str) -> str:
        raw = f"{message.id}|{text}|{cls._snapshot(message)}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _find_next_button(message: Message) -> tuple[int, int] | None:
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        for row_index, row in enumerate(rows):
            for col_index, button in enumerate(row):
                label = (getattr(button, "text", "") or "").strip().casefold()
                if "next" in label or "➡" in label or "▶" in label:
                    return row_index, col_index
        return None

    async def _click_button(
        self,
        client: Client,
        message: Message,
        row_index: int,
        col_index: int,
    ) -> None:
        button = message.reply_markup.inline_keyboard[row_index][col_index]
        callback_data = getattr(button, "callback_data", None)

        async def click() -> object:
            if callback_data is not None:
                return await client.request_callback_answer(
                    chat_id=message.chat.id,
                    message_id=message.id,
                    callback_data=callback_data,
                    timeout=max(10, int(self.page_timeout)),
                )
            return await message.click(getattr(button, "text", ""), timeout=10)

        await run_with_retries(
            click,
            attempts=self.max_retries,
            label=f"click next on @{self.bot_username}",
        )
