from __future__ import annotations

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from bot.main import AppContext
from services.job_queue import GiftJob
from utils.permissions import is_gift_group, is_owner

_COMMANDS = ["cstart1", "cstart2", "sstart1", "sstart2"]


async def _gift_start_handler(ctx: AppContext, message: Message) -> None:
    if not is_owner(message, ctx.settings.owner_ids):
        return
    if not is_gift_group(message, ctx.settings.gift_group_id):
        await message.reply_text("⚠️ This command can only be used in the configured Gift Group.")
        return
    if not message.reply_to_message:
        await message.reply_text(
            "⚠️ Reply to the target user's message, then send one of:\n"
            "/cstart1 /cstart2 /sstart1 /sstart2"
        )
        return

    command = (message.command or [""])[0].lower()
    service = "character" if command.startswith("c") else "senpai"
    slot = int(command[-1])

    if not ctx.session_manager.is_connected(slot):
        await message.reply_text(
            f"❌ Session {slot} is not connected.\n"
            f"Connect it in bot DM with /connect{slot} <StringSession>."
        )
        return

    target = message.reply_to_message
    target_user_id = target.from_user.id if target.from_user else None
    service_name = "Character Catcher" if service == "character" else "SenpaiCatcher"

    status = await message.reply_text(
        (
            "🕒 JOB QUEUED\n\n"
            f"Service: {service_name}\n"
            f"Session: {slot}\n"
            "Preparing queue..."
        )
    )

    job = GiftJob(
        slot=slot,
        service=service,
        group_id=message.chat.id,
        target_message_id=target.id,
        target_user_id=target_user_id,
        owner_id=message.from_user.id,
        status_chat_id=status.chat.id,
        status_message_id=status.id,
        command_message_id=message.id,
    )

    try:
        position = await ctx.job_queue.enqueue(job)
    except Exception as exc:
        await status.edit_text(
            f"❌ Could not queue job\n\n{type(exc).__name__}: {exc}"
        )
        return

    await status.edit_text(
        (
            "🕒 JOB QUEUED\n\n"
            f"Service: {service_name}\n"
            f"Session: {slot}\n"
            f"Queue position: {position}\n"
            f"Job: {job.job_id[:8]}"
        )
    )


def register_gift_handlers(ctx: AppContext) -> None:
    async def callback(_client, message: Message) -> None:
        await _gift_start_handler(ctx, message)

    ctx.bot.add_handler(MessageHandler(callback, filters.command(_COMMANDS)))
