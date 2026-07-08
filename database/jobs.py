from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


class JobsRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection = db["gift_jobs"]

    async def create(self, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        payload = dict(data)
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        await self._collection.insert_one(payload)

    async def update(self, job_id: str, **fields: Any) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._collection.update_one({"_id": job_id}, {"$set": fields})

    async def mark_unfinished_as_interrupted(self) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_many(
            {"status": {"$in": ["queued", "running", "scanning", "gifting"]}},
            {
                "$set": {
                    "status": "interrupted",
                    "error": "Application restarted before the job completed",
                    "updated_at": now,
                    "finished_at": now,
                }
            },
        )
