from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.types import Message

from clients.session_locks import SessionLocks
from clients.session_manager import SessionManager
from database.jobs import JobsRepository
from services.character_catcher import CharacterCatcherService
from services.job_queue import GiftJob, JobResult
from services.senpai_catcher import SenpaiCatcherService
from utils.logger import get_logger
from utils.retry import run_with_retries

log = get_logger(__name__)


class GiftService:
    def __init__(
        self,
        *,
        bot_client: Client,
        session_manager: SessionManager,
        session_locks: SessionLocks,
        character_service: CharacterCatcherService,
        senpai_service: SenpaiCatcherService,
        jobs_repo: JobsRepository,
        gift_command: str,
        character_bot_id: int,
        senpai_bot_id: int,
        gift_confirm_timeout: float,
        gift_result_timeout: float,
        gift_delay: float,
        max_retries: int,
    ) -> None:
        self.bot_client = bot_client
        self.session_manager = session_manager
        self.session_locks = session_locks
        self.character_service = character_service
        self.senpai_service = senpai_service
        self.jobs_repo = jobs_repo
        self.gift_command = gift_command
        self.character_bot_id = character_bot_id
        self.senpai_bot_id = senpai_bot_id
        self.gift_confirm_timeout = gift_confirm_timeout
        self.gift_result_timeout = gift_result_timeout
        self.gift_delay = gift_delay
        self.max_retries = max_retries

    async def run_job(self, job: GiftJob, cancel_event: asyncio.Event) -> JobResult:
        client = self.session_manager.get_client(job.slot)
        service = self._service_for(job.service)
        target_bot_id = self._bot_id_for(job.service)

        async with self.session_locks.lock(job.slot):
            await self.jobs_repo.update(job.job_id, status="scanning")
            await self._edit_status(
                job,
                self._status_text(
                    title="🔎 Scanning harem...",
                    job=job,
                    detail=f"Service: {service.display_name}\nSession: {job.slot}",
                ),
            )

            try:
                ids = await service.collect_ids(client)
            except Exception as exc:
                await self._edit_status(
                    job,
                    self._status_text(
                        title="❌ Harem scan failed",
                        job=job,
                        detail=f"{type(exc).__name__}: {exc}",
                    ),
                )
                return JobResult(status="failed", error=f"scan failed: {exc}")

            total = len(ids)
            await self.jobs_repo.update(job.job_id, status="gifting", total=total)
            await self._edit_status(
                job,
                self._status_text(
                    title="🎁 Gift job started",
                    job=job,
                    detail=f"IDs found: {total}\nProgress: 0/{total}",
                ),
            )

            successful = 0
            failed = 0
            skipped = 0
            failed_ids: list[int] = []

            for index, item_id in enumerate(ids, start=1):
                if cancel_event.is_set():
                    skipped = total - (successful + failed)
                    await self._edit_status(
                        job,
                        self._status_text(
                            title="🛑 Gift job cancelled",
                            job=job,
                            detail=(
                                f"Total: {total}\n"
                                f"Successful: {successful}\n"
                                f"Failed: {failed}\n"
                                f"Skipped: {skipped}"
                            ),
                        ),
                    )
                    return JobResult(
                        status="cancelled",
                        total=total,
                        successful=successful,
                        failed=failed,
                        skipped=skipped,
                        error="Cancelled by session clear request",
                    )

                try:
                    await self._gift_one(
                        client=client,
                        group_id=job.group_id,
                        target_message_id=job.target_message_id,
                        target_bot_id=target_bot_id,
                        item_id=item_id,
                    )
                    successful += 1
                except Exception as exc:
                    failed += 1
                    failed_ids.append(item_id)
                    log.warning(
                        "Gift failed job=%s id=%s error=%s",
                        job.job_id,
                        item_id,
                        type(exc).__name__,
                    )

                if index == 1 or index % 5 == 0 or index == total:
                    await self.jobs_repo.update(
                        job.job_id,
                        successful=successful,
                        failed=failed,
                        current_index=index,
                        failed_ids=failed_ids[-100:],
                    )
                    await self._edit_status(
                        job,
                        self._status_text(
                            title="🎁 Sending gifts...",
                            job=job,
                            detail=(
                                f"Progress: {index}/{total}\n"
                                f"Successful: {successful}\n"
                                f"Failed: {failed}\n"
                                f"Current ID: {item_id}"
                            ),
                        ),
                    )

                if index < total and self.gift_delay > 0:
                    await asyncio.sleep(self.gift_delay)

            final_status = "completed" if failed == 0 else "completed_with_errors"
            failed_preview = ", ".join(map(str, failed_ids[:20]))
            extra = f"\nFailed IDs: {failed_preview}" if failed_preview else ""
            await self._edit_status(
                job,
                self._status_text(
                    title="✅ Gift job completed",
                    job=job,
                    detail=(
                        f"Total: {total}\n"
                        f"Successful: {successful}\n"
                        f"Failed: {failed}{extra}"
                    ),
                ),
            )
            return JobResult(
                status=final_status,
                total=total,
                successful=successful,
                failed=failed,
                skipped=0,
                error=None if failed == 0 else f"{failed} gift(s) failed",
            )

    def _service_for(self, service: str):
        if service == "character":
            return self.character_service
        if service == "senpai":
            return self.senpai_service
        raise ValueError(f"Unknown service: {service}")

    def _bot_id_for(self, service: str) -> int:
        if service == "character":
            return self.character_bot_id
        if service == "senpai":
            return self.senpai_bot_id
        raise ValueError(f"Unknown service: {service}")

    async def _gift_one(
        self,
        *,
        client: Client,
        group_id: int,
        target_message_id: int,
        target_bot_id: int,
        item_id: int,
    ) -> None:
        async def send_gift() -> Message:
            return await client.send_message(
                chat_id=group_id,
                text=f"{self.gift_command} {item_id}",
                reply_to_message_id=target_message_id,
            )

        sent = await run_with_retries(
            send_gift,
            attempts=self.max_retries,
            label=f"send gift {item_id}",
        )

        confirmation = await self._wait_for_confirmation(
            client=client,
            group_id=group_id,
            target_bot_id=target_bot_id,
            sent_message=sent,
        )
        button_pos = self._find_confirm_button(confirmation)
        if button_pos is None:
            raise RuntimeError(f"Confirm button not found for gift ID {item_id}")

        row_index, col_index = button_pos
        button = confirmation.reply_markup.inline_keyboard[row_index][col_index]
        before = self._message_snapshot(confirmation)

        async def click_confirm() -> object:
            callback_data = getattr(button, "callback_data", None)
            if callback_data is not None:
                return await client.request_callback_answer(
                    chat_id=confirmation.chat.id,
                    message_id=confirmation.id,
                    callback_data=callback_data,
                    timeout=max(10, int(self.gift_confirm_timeout)),
                )
            return await confirmation.click(getattr(button, "text", ""), timeout=10)

        await run_with_retries(
            click_confirm,
            attempts=self.max_retries,
            label=f"confirm gift {item_id}",
        )

        # Some target bots edit the confirmation message, while others only
        # answer the callback. We wait briefly for either behavior but do not
        # fail a successfully answered callback just because no edit appears.
        await self._wait_for_result_change(
            client=client,
            group_id=group_id,
            message=confirmation,
            before_snapshot=before,
            target_bot_id=target_bot_id,
        )

    async def _wait_for_confirmation(
        self,
        *,
        client: Client,
        group_id: int,
        target_bot_id: int,
        sent_message: Message,
    ) -> Message:
        deadline = time.monotonic() + self.gift_confirm_timeout
        fallback: Message | None = None

        while time.monotonic() < deadline:
            async for candidate in client.get_chat_history(group_id, limit=30):
                if candidate.id <= sent_message.id:
                    continue
                if not candidate.from_user or candidate.from_user.id != target_bot_id:
                    continue
                if self._find_confirm_button(candidate) is None:
                    continue

                if candidate.reply_to_message_id == sent_message.id:
                    return candidate
                if fallback is None:
                    fallback = candidate

            if fallback is not None:
                # Brief grace period allows a direct reply to appear before
                # using the newest matching confirmation as a fallback.
                await asyncio.sleep(1.0)
                return fallback
            await asyncio.sleep(0.8)

        raise TimeoutError(
            f"Timed out waiting for confirmation for gift ID message {sent_message.id}"
        )

    @staticmethod
    def _find_confirm_button(message: Message) -> tuple[int, int] | None:
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        for row_index, row in enumerate(rows):
            for col_index, button in enumerate(row):
                label = (getattr(button, "text", "") or "").strip().casefold()
                if any(bad in label for bad in ("cancel", "no", "❌")):
                    continue
                if any(good in label for good in ("confirm", "yes", "✅", "အတည်ပြု")):
                    return row_index, col_index
        return None

    async def _wait_for_result_change(
        self,
        *,
        client: Client,
        group_id: int,
        message: Message,
        before_snapshot: str,
        target_bot_id: int,
    ) -> None:
        if self.gift_result_timeout <= 0:
            return
        deadline = time.monotonic() + self.gift_result_timeout
        while time.monotonic() < deadline:
            try:
                refreshed = await client.get_messages(group_id, message.id)
                if refreshed and self._message_snapshot(refreshed) != before_snapshot:
                    return
                async for candidate in client.get_chat_history(group_id, limit=8):
                    if candidate.id <= message.id:
                        continue
                    if candidate.from_user and candidate.from_user.id == target_bot_id:
                        return
            except Exception:
                return
            await asyncio.sleep(0.6)

    @staticmethod
    def _message_snapshot(message: Message) -> str:
        text = message.text or message.caption or ""
        labels: list[str] = []
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        for row in rows:
            for button in row:
                labels.append(getattr(button, "text", "") or "")
        return f"{message.id}|{text}|{'|'.join(labels)}"

    async def _edit_status(self, job: GiftJob, text: str) -> None:
        try:
            await self.bot_client.edit_message_text(
                chat_id=job.status_chat_id,
                message_id=job.status_message_id,
                text=text,
            )
        except Exception as exc:
            log.debug("Could not edit status message for job %s: %s", job.job_id, exc)

    @staticmethod
    def _status_text(*, title: str, job: GiftJob, detail: str) -> str:
        service_name = "Character Catcher" if job.service == "character" else "SenpaiCatcher"
        return (
            f"{title}\n\n"
            f"Service: {service_name}\n"
            f"Session: {job.slot}\n"
            f"Job: {job.job_id[:8]}\n\n"
            f"{detail}"
        )
