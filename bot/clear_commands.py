from __future__ import annotations

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from bot.main import AppContext
from utils.permissions import is_owner, is_private


async def _clear_handler(ctx: AppContext, message: Message) -> None:
    if not is_owner(message, ctx.settings.owner_ids):
        return
    if not is_private(message):
        await message.reply_text("⚠️ /clearss1 and /clearss2 can only be used in bot DM.")
        return

    command = (message.command or [""])[0].lower()
    slot = 1 if command.startswith("clearss1") else 2

    active = ctx.job_queue.active_job(slot)
    pending = ctx.job_queue.pending_count(slot)
    if active or pending:
        progress = await message.reply_text(
            f"🛑 Stopping Session {slot} jobs safely...\n"
            "The current gift operation will stop between IDs."
        )
        cancelled_pending, active_was_running = await ctx.job_queue.cancel_slot(slot)
        cleared = await ctx.session_manager.clear_slot(slot)
        await progress.edit_text(
            (
                f"✅ SESSION {slot} CLEARED\n\n"
                f"Active job stopped: {'Yes' if active_was_running else 'No'}\n"
                f"Queued jobs cancelled: {cancelled_pending}\n"
                f"Stored session removed: {'Yes' if cleared else 'Not found'}"
            )
        )
        return

    cleared = await ctx.session_manager.clear_slot(slot)
    if cleared:
        await message.reply_text(f"✅ SESSION {slot} CLEARED\n\nAccount disconnected and stored session removed.")
    else:
        await message.reply_text(f"⚠️ SESSION {slot} NOT FOUND\n\nNo connected or stored session exists.")


def register_clear_handlers(ctx: AppContext) -> None:
    async def callback(_client, message: Message) -> None:
        await _clear_handler(ctx, message)

    ctx.bot.add_handler(
        MessageHandler(callback, filters.command(["clearss1", "clearss2"]))
    )
