from __future__ import annotations

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from bot.main import AppContext
from utils.logger import get_logger
from utils.permissions import is_owner, is_private

log = get_logger(__name__)


async def _connect_handler(ctx: AppContext, message: Message) -> None:
    if not is_owner(message, ctx.settings.owner_ids):
        return
    if not is_private(message):
        await message.reply_text("⚠️ /connect1 and /connect2 can only be used in bot DM.")
        return

    command = (message.command or [""])[0].lower()
    slot = 1 if command.startswith("connect1") else 2
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        await message.reply_text(f"Usage: /connect{slot} <Pyrogram StringSession>")
        return

    session_string = parts[1].strip()

    if ctx.job_queue.active_job(slot) or ctx.job_queue.pending_count(slot):
        try:
            await message.delete()
        except Exception:
            pass
        await ctx.bot.send_message(
            message.chat.id,
            f"⚠️ Session {slot} is busy. Wait for its jobs to finish or use /clearss{slot} first.",
        )
        return

    try:
        # Remove the credential-bearing command from chat history before doing
        # longer network work. Failure to delete does not block the connection.
        try:
            await message.delete()
        except Exception:
            pass

        account = await ctx.session_manager.connect_slot(slot, session_string)
        username = f"@{account.username}" if account.username else "None"
        await ctx.bot.send_message(
            message.chat.id,
            (
                "✅ SESSION CONNECTED\n\n"
                f"Slot: Session {slot}\n"
                f"Account: {account.display_name}\n"
                f"Username: {username}\n"
                f"User ID: {account.user_id}\n\n"
                "Available services:\n"
                "• Character Catcher\n"
                "• SenpaiCatcher"
            ),
        )
    except Exception as exc:
        log.warning("Session %s connection failed: %s", slot, type(exc).__name__)
        await ctx.bot.send_message(
            message.chat.id,
            (
                "❌ SESSION CONNECTION ERROR\n\n"
                f"Slot: Session {slot}\n"
                f"Reason: {type(exc).__name__}: {exc}"
            ),
        )


def register_connect_handlers(ctx: AppContext) -> None:
    async def callback(_client, message: Message) -> None:
        await _connect_handler(ctx, message)

    ctx.bot.add_handler(
        MessageHandler(callback, filters.command(["connect1", "connect2"]))
    )
