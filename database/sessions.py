from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from utils.encryption import EncryptionService


class SessionsRepository:
    def __init__(self, db: AsyncDatabase, encryption: EncryptionService) -> None:
        self._collection = db["user_sessions"]
        self._encryption = encryption

    async def save(
        self,
        *,
        slot: int,
        session_string: str,
        account_id: int,
        first_name: str,
        last_name: str | None,
        username: str | None,
    ) -> None:
        encrypted = self._encryption.encrypt(session_string)
        await self._collection.update_one(
            {"_id": slot},
            {
                "$set": {
                    "session_encrypted": encrypted,
                    "account_id": account_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def get(self, slot: int) -> dict[str, Any] | None:
        return await self._collection.find_one({"_id": slot})

    async def list_all(self) -> list[dict[str, Any]]:
        return await self._collection.find({"_id": {"$in": [1, 2]}}).to_list(length=2)

    async def delete(self, slot: int) -> int:
        result = await self._collection.delete_one({"_id": slot})
        return result.deleted_count

    def decrypt_document(self, document: dict[str, Any]) -> str:
        encrypted = document.get("session_encrypted")
        if not encrypted:
            raise ValueError("Stored session document has no encrypted session")
        return self._encryption.decrypt(encrypted)
