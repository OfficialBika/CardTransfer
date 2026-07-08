from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyrogram import Client

from clients.client_factory import ClientFactory
from database.sessions import SessionsRepository
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConnectedAccount:
    slot: int
    user_id: int
    first_name: str
    last_name: str | None
    username: str | None

    @property
    def display_name(self) -> str:
        full = " ".join(part for part in [self.first_name, self.last_name] if part)
        return full or str(self.user_id)


class SessionManager:
    def __init__(
        self,
        client_factory: ClientFactory,
        sessions_repo: SessionsRepository,
    ) -> None:
        self._factory = client_factory
        self._repo = sessions_repo
        self._clients: dict[int, Client] = {}
        self._accounts: dict[int, ConnectedAccount] = {}
        self._guard = asyncio.Lock()

    @staticmethod
    def _validate_slot(slot: int) -> None:
        if slot not in (1, 2):
            raise ValueError("Session slot must be 1 or 2")

    async def connect_slot(self, slot: int, session_string: str) -> ConnectedAccount:
        self._validate_slot(slot)
        session_string = session_string.strip()
        if not session_string:
            raise ValueError("StringSession is empty")

        async with self._guard:
            candidate = self._factory.create_user_client(slot, session_string)
            old_client = self._clients.get(slot)
            started = False
            try:
                await candidate.start()
                started = True
                me = await candidate.get_me()
                if getattr(me, "is_bot", False):
                    raise ValueError("The supplied session belongs to a bot account, not a user account")

                account = ConnectedAccount(
                    slot=slot,
                    user_id=me.id,
                    first_name=me.first_name or "Telegram User",
                    last_name=me.last_name,
                    username=me.username,
                )

                await self._repo.save(
                    slot=slot,
                    session_string=session_string,
                    account_id=account.user_id,
                    first_name=account.first_name,
                    last_name=account.last_name,
                    username=account.username,
                )

                self._clients[slot] = candidate
                self._accounts[slot] = account

                if old_client and old_client is not candidate:
                    try:
                        await old_client.stop()
                    except Exception:
                        log.exception("Failed stopping previous client for slot %s", slot)

                log.info("Session slot %s connected for account id=%s", slot, account.user_id)
                return account
            except Exception:
                if started:
                    try:
                        await candidate.stop()
                    except Exception:
                        pass
                raise

    async def restore_all(self) -> dict[int, bool]:
        results: dict[int, bool] = {1: False, 2: False}
        documents = await self._repo.list_all()
        for doc in documents:
            slot = int(doc["_id"])
            if slot not in (1, 2):
                continue
            try:
                session_string = self._repo.decrypt_document(doc)
                candidate = self._factory.create_user_client(slot, session_string)
                await candidate.start()
                me = await candidate.get_me()
                if getattr(me, "is_bot", False):
                    raise ValueError("Stored session is a bot account")
                self._clients[slot] = candidate
                self._accounts[slot] = ConnectedAccount(
                    slot=slot,
                    user_id=me.id,
                    first_name=me.first_name or "Telegram User",
                    last_name=me.last_name,
                    username=me.username,
                )
                results[slot] = True
                log.info("Restored session slot %s for account id=%s", slot, me.id)
            except Exception as exc:
                log.error("Could not restore session slot %s: %s", slot, type(exc).__name__)
        return results

    async def clear_slot(self, slot: int) -> bool:
        self._validate_slot(slot)
        async with self._guard:
            client = self._clients.pop(slot, None)
            self._accounts.pop(slot, None)
            if client:
                try:
                    await client.stop()
                except Exception:
                    log.exception("Error stopping client for slot %s", slot)
            deleted = await self._repo.delete(slot)
            log.info("Session slot %s cleared", slot)
            return bool(client or deleted)

    def is_connected(self, slot: int) -> bool:
        self._validate_slot(slot)
        client = self._clients.get(slot)
        return bool(client and client.is_connected)

    def get_client(self, slot: int) -> Client:
        self._validate_slot(slot)
        client = self._clients.get(slot)
        if not client or not client.is_connected:
            raise RuntimeError(f"Session {slot} is not connected")
        return client

    def get_account(self, slot: int) -> ConnectedAccount | None:
        self._validate_slot(slot)
        return self._accounts.get(slot)

    async def shutdown(self) -> None:
        async with self._guard:
            clients = list(self._clients.items())
            self._clients.clear()
            self._accounts.clear()
        for slot, client in clients:
            try:
                if client.is_connected:
                    await client.stop()
            except Exception:
                log.exception("Failed to stop session slot %s during shutdown", slot)
