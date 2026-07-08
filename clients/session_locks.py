from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class SessionLocks:
    def __init__(self) -> None:
        self._locks = {1: asyncio.Lock(), 2: asyncio.Lock()}

    @asynccontextmanager
    async def lock(self, slot: int) -> AsyncIterator[None]:
        if slot not in self._locks:
            raise ValueError(f"Unsupported session slot: {slot}")
        async with self._locks[slot]:
            yield

    def is_locked(self, slot: int) -> bool:
        if slot not in self._locks:
            return False
        return self._locks[slot].locked()
