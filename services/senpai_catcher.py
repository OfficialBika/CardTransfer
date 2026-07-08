from __future__ import annotations

from pyrogram import Client

from parsers.senpai_parser import parse_senpai_ids
from services.pagination import PaginationScanner


class SenpaiCatcherService:
    service_key = "senpai"
    display_name = "SenpaiCatcher"

    def __init__(
        self,
        *,
        bot_username: str,
        bot_id: int,
        harem_command: str,
        page_timeout: float,
        max_pages: int,
        max_retries: int,
    ) -> None:
        self.bot_id = bot_id
        self.scanner = PaginationScanner(
            bot_username=bot_username,
            bot_id=bot_id,
            harem_command=harem_command,
            parser=parse_senpai_ids,
            page_timeout=page_timeout,
            max_pages=max_pages,
            max_retries=max_retries,
        )

    async def collect_ids(self, client: Client) -> list[int]:
        return await self.scanner.scan(client)
