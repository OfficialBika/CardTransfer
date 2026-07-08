from __future__ import annotations

from collections.abc import Collection

from pyrogram.enums import ChatType
from pyrogram.types import Message


def is_owner(message: Message, owner_ids: Collection[int]) -> bool:
    return bool(message.from_user and message.from_user.id in owner_ids)


def is_private(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE


def is_gift_group(message: Message, gift_group_id: int) -> bool:
    return message.chat.id == gift_group_id
