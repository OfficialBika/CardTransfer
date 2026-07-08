from __future__ import annotations

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from utils.logger import get_logger

log = get_logger(__name__)


class MongoDatabase:
    def __init__(self, uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(uri, serverSelectionTimeoutMS=15000)
        self.db: AsyncDatabase = self._client[db_name]

    async def connect(self) -> None:
        await self._client.admin.command("ping")
        log.info("MongoDB connected")

    async def close(self) -> None:
        await self._client.close()
        log.info("MongoDB connection closed")
