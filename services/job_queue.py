from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from database.jobs import JobsRepository
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class GiftJob:
    slot: int
    service: str
    group_id: int
    target_message_id: int
    target_user_id: int | None
    owner_id: int
    status_chat_id: int
    status_message_id: int
    command_message_id: int
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_document(self) -> dict[str, object]:
        return {
            "_id": self.job_id,
            "slot": self.slot,
            "service": self.service,
            "group_id": self.group_id,
            "target_message_id": self.target_message_id,
            "target_user_id": self.target_user_id,
            "owner_id": self.owner_id,
            "status_chat_id": self.status_chat_id,
            "status_message_id": self.status_message_id,
            "command_message_id": self.command_message_id,
            "status": "queued",
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class JobResult:
    status: str
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    error: str | None = None


Runner = Callable[[GiftJob, asyncio.Event], Awaitable[JobResult]]


class JobQueue:
    def __init__(self, *, jobs_repo: JobsRepository, runner: Runner) -> None:
        self._jobs_repo = jobs_repo
        self._runner = runner
        self._queues: dict[int, asyncio.Queue[GiftJob | None]] = {
            1: asyncio.Queue(),
            2: asyncio.Queue(),
        }
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._active: dict[int, GiftJob | None] = {1: None, 2: None}
        self._cancel_events: dict[int, asyncio.Event] = {
            1: asyncio.Event(),
            2: asyncio.Event(),
        }
        self._active_done: dict[int, asyncio.Event] = {
            1: asyncio.Event(),
            2: asyncio.Event(),
        }
        self._active_done[1].set()
        self._active_done[2].set()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for slot in (1, 2):
            self._workers[slot] = asyncio.create_task(
                self._worker(slot), name=f"gift-worker-{slot}"
            )
        log.info("Gift job workers started")

    async def enqueue(self, job: GiftJob) -> int:
        if job.slot not in (1, 2):
            raise ValueError("Job slot must be 1 or 2")
        if not self._started:
            raise RuntimeError("Job queue is not started")

        await self._jobs_repo.create(job.to_document())
        queue = self._queues[job.slot]
        ahead = queue.qsize() + (1 if self._active[job.slot] else 0)
        await queue.put(job)
        return ahead + 1

    async def cancel_slot(self, slot: int, wait_timeout: float = 60.0) -> tuple[int, bool]:
        if slot not in (1, 2):
            raise ValueError("Session slot must be 1 or 2")

        active_was_running = self._active[slot] is not None
        if active_was_running:
            self._cancel_events[slot].set()

        cancelled_pending = 0
        queue = self._queues[slot]
        kept_sentinel = False
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if item is None:
                    kept_sentinel = True
                    continue
                cancelled_pending += 1
                await self._jobs_repo.update(
                    item.job_id,
                    status="cancelled",
                    error="Cancelled because the session was cleared",
                    finished_at=datetime.now(timezone.utc),
                )
            finally:
                queue.task_done()

        if kept_sentinel:
            await queue.put(None)

        if active_was_running:
            try:
                await asyncio.wait_for(self._active_done[slot].wait(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                log.warning("Timed out waiting for active slot %s job to stop", slot)

        return cancelled_pending, active_was_running

    def pending_count(self, slot: int) -> int:
        return self._queues[slot].qsize()

    def active_job(self, slot: int) -> GiftJob | None:
        return self._active[slot]

    async def _worker(self, slot: int) -> None:
        queue = self._queues[slot]
        while True:
            job = await queue.get()
            try:
                if job is None:
                    return

                self._active[slot] = job
                self._active_done[slot].clear()
                cancel_event = self._cancel_events[slot]
                cancel_event.clear()

                await self._jobs_repo.update(
                    job.job_id,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )

                try:
                    result = await self._runner(job, cancel_event)
                except asyncio.CancelledError:
                    await self._jobs_repo.update(
                        job.job_id,
                        status="interrupted",
                        error="Worker was cancelled",
                        finished_at=datetime.now(timezone.utc),
                    )
                    raise
                except Exception as exc:
                    log.exception("Gift job %s failed", job.job_id)
                    await self._jobs_repo.update(
                        job.job_id,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                        finished_at=datetime.now(timezone.utc),
                    )
                else:
                    await self._jobs_repo.update(
                        job.job_id,
                        status=result.status,
                        total=result.total,
                        successful=result.successful,
                        failed=result.failed,
                        skipped=result.skipped,
                        error=result.error,
                        finished_at=datetime.now(timezone.utc),
                    )
            finally:
                if job is not None:
                    self._active[slot] = None
                    self._cancel_events[slot].clear()
                    self._active_done[slot].set()
                queue.task_done()

    async def shutdown(self) -> None:
        if not self._started:
            return
        for slot in (1, 2):
            self._cancel_events[slot].set()

        for slot in (1, 2):
            await self._queues[slot].put(None)

        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers.values(), return_exceptions=True),
                timeout=90,
            )
        except asyncio.TimeoutError:
            for task in self._workers.values():
                task.cancel()
            await asyncio.gather(*self._workers.values(), return_exceptions=True)

        self._workers.clear()
        self._started = False
        log.info("Gift job workers stopped")
