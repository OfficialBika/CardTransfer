from __future__ import annotations

import os
from dataclasses import dataclass
from typing import FrozenSet

from pyrogram import Client

from clients.session_manager import SessionManager
from services.job_queue import JobQueue


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_owner_ids(raw: str) -> FrozenSet[int]:
    values: set[int] = set()
    for item in raw.replace(" ", "").split(","):
        if item:
            values.add(int(item))
    if not values:
        raise RuntimeError("OWNER_IDS must contain at least one Telegram user ID")
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    owner_ids: FrozenSet[int]
    mongo_uri: str
    db_name: str
    encryption_key: str
    gift_group_id: int
    character_bot_username: str
    character_bot_id: int
    senpai_bot_username: str
    senpai_bot_id: int
    harem_command: str
    gift_command: str
    page_timeout: float
    gift_confirm_timeout: float
    gift_result_timeout: float
    max_pages: int
    gift_delay: float
    max_retries: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bot_token=_require_env("BOT_TOKEN"),
            api_id=int(_require_env("API_ID")),
            api_hash=_require_env("API_HASH"),
            owner_ids=_parse_owner_ids(_require_env("OWNER_IDS")),
            mongo_uri=_require_env("MONGO_URI"),
            db_name=os.getenv("DB_NAME", "bika_gift_bot").strip() or "bika_gift_bot",
            encryption_key=_require_env("SESSION_ENCRYPTION_KEY"),
            gift_group_id=int(os.getenv("GIFT_GROUP_ID", "-1004294757492")),
            character_bot_username=os.getenv(
                "CHARACTER_BOT_USERNAME", "Character_Catcher_Bot"
            ).strip().lstrip("@"),
            character_bot_id=int(os.getenv("CHARACTER_BOT_ID", "6157455819")),
            senpai_bot_username=os.getenv("SENPAI_BOT_USERNAME", "SenpaiCatcherBot").strip().lstrip("@"),
            senpai_bot_id=int(os.getenv("SENPAI_BOT_ID", "8532697507")),
            harem_command=os.getenv("HAREM_COMMAND", "/harem").strip() or "/harem",
            gift_command=os.getenv("GIFT_COMMAND", "/gift").strip() or "/gift",
            page_timeout=float(os.getenv("PAGE_TIMEOUT", "35")),
            gift_confirm_timeout=float(os.getenv("GIFT_CONFIRM_TIMEOUT", "30")),
            gift_result_timeout=float(os.getenv("GIFT_RESULT_TIMEOUT", "8")),
            max_pages=int(os.getenv("MAX_PAGES", "100")),
            gift_delay=float(os.getenv("GIFT_DELAY", "2.0")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


@dataclass(slots=True)
class AppContext:
    settings: Settings
    bot: Client
    session_manager: SessionManager
    job_queue: JobQueue


def register_handlers(ctx: AppContext) -> None:
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message

    from bot.clear_commands import register_clear_handlers
    from bot.connect_commands import register_connect_handlers
    from bot.gift_commands import register_gift_handlers
    from utils.permissions import is_owner

    async def help_handler(_client, message: Message) -> None:
        if not is_owner(message, ctx.settings.owner_ids):
            return
        lines = [
            "🎁 Bika Gift Bot",
            "",
            "Session setup (DM only):",
            "/connect1 <StringSession>",
            "/connect2 <StringSession>",
            "/clearss1",
            "/clearss2",
            "/sessionstatus",
            "",
            "Reply commands in Gift Group:",
            "/cstart1  → Character Catcher / Session 1",
            "/cstart2  → Character Catcher / Session 2",
            "/sstart1  → SenpaiCatcher / Session 1",
            "/sstart2  → SenpaiCatcher / Session 2",
        ]
        await message.reply_text("\n".join(lines))

    async def status_handler(_client, message: Message) -> None:
        if not is_owner(message, ctx.settings.owner_ids):
            return
        lines = ["📡 SESSION STATUS", ""]
        for slot in (1, 2):
            account = ctx.session_manager.get_account(slot)
            if account and ctx.session_manager.is_connected(slot):
                username = f"@{account.username}" if account.username else "No username"
                active = ctx.job_queue.active_job(slot)
                state = f"Busy ({active.service})" if active else "Ready"
                lines.extend([
                    f"Session {slot}: ✅ Connected",
                    f"Account: {account.display_name}",
                    f"Username: {username}",
                    f"State: {state}",
                    f"Queued: {ctx.job_queue.pending_count(slot)}",
                    "",
                ])
            else:
                lines.extend([f"Session {slot}: ❌ Not connected", ""])
        await message.reply_text("\n".join(lines).strip())

    ctx.bot.add_handler(MessageHandler(help_handler, filters.command(["start", "help"])))
    ctx.bot.add_handler(MessageHandler(status_handler, filters.command("sessionstatus")))

    register_connect_handlers(ctx)
    register_clear_handlers(ctx)
    register_gift_handlers(ctx)
