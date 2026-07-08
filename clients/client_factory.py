from __future__ import annotations

import secrets

from pyrogram import Client


class ClientFactory:
    def __init__(self, api_id: int, api_hash: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash

    def create_user_client(self, slot: int, session_string: str) -> Client:
        return Client(
            name=f"bika_gift_slot_{slot}_{secrets.token_hex(4)}",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=session_string,
            in_memory=True,
            no_updates=True,
            sleep_threshold=15,
        )
