from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pyrogram.errors import FloodWait

from utils.logger import get_logger

T = TypeVar("T")
log = get_logger(__name__)


async def run_with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "operation",
) -> T:
    if attempts < 1:
        attempts = 1

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except FloodWait as exc:
            last_error = exc
            wait_for = max(float(exc.value), 1.0) + 0.5
            log.warning("%s hit FloodWait; sleeping %.1fs", label, wait_for)
            await asyncio.sleep(wait_for)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "%s failed on attempt %s/%s with %s; retrying in %.1fs",
                label,
                attempt,
                attempts,
                type(exc).__name__,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error
