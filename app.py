from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from pyrogram import Client, idle

from bot.main import AppContext, Settings, register_handlers
from clients.client_factory import ClientFactory
from clients.session_locks import SessionLocks
from clients.session_manager import SessionManager
from database.jobs import JobsRepository
from database.mongodb import MongoDatabase
from database.sessions import SessionsRepository
from services.character_catcher import CharacterCatcherService
from services.gift_service import GiftService
from services.job_queue import JobQueue
from services.senpai_catcher import SenpaiCatcherService
from utils.encryption import EncryptionService
from utils.logger import configure_logging, get_logger


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    log = get_logger(__name__)

    database = MongoDatabase(settings.mongo_uri, settings.db_name)
    await database.connect()

    encryption = EncryptionService(settings.encryption_key)
    sessions_repo = SessionsRepository(database.db, encryption)
    jobs_repo = JobsRepository(database.db)
    await jobs_repo.mark_unfinished_as_interrupted()

    client_factory = ClientFactory(settings.api_id, settings.api_hash)
    session_manager = SessionManager(client_factory, sessions_repo)
    session_locks = SessionLocks()

    character_service = CharacterCatcherService(
        bot_username=settings.character_bot_username,
        bot_id=settings.character_bot_id,
        harem_command=settings.harem_command,
        page_timeout=settings.page_timeout,
        max_pages=settings.max_pages,
        max_retries=settings.max_retries,
    )
    senpai_service = SenpaiCatcherService(
        bot_username=settings.senpai_bot_username,
        bot_id=settings.senpai_bot_id,
        harem_command=settings.harem_command,
        page_timeout=settings.page_timeout,
        max_pages=settings.max_pages,
        max_retries=settings.max_retries,
    )

    bot = Client(
        name="bika_gift_main_bot",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        in_memory=True,
        workers=8,
    )

    gift_service = GiftService(
        bot_client=bot,
        session_manager=session_manager,
        session_locks=session_locks,
        character_service=character_service,
        senpai_service=senpai_service,
        jobs_repo=jobs_repo,
        gift_command=settings.gift_command,
        character_bot_id=settings.character_bot_id,
        senpai_bot_id=settings.senpai_bot_id,
        gift_confirm_timeout=settings.gift_confirm_timeout,
        gift_result_timeout=settings.gift_result_timeout,
        gift_delay=settings.gift_delay,
        max_retries=settings.max_retries,
    )

    job_queue = JobQueue(jobs_repo=jobs_repo, runner=gift_service.run_job)
    ctx = AppContext(
        settings=settings,
        bot=bot,
        session_manager=session_manager,
        job_queue=job_queue,
    )
    register_handlers(ctx)

    try:
        await bot.start()
        await session_manager.restore_all()
        await job_queue.start()
        me = await bot.get_me()
        log.info("Bika Gift Bot started as @%s", me.username or me.first_name)
        await idle()
    finally:
        log.info("Shutting down Bika Gift Bot")
        await job_queue.shutdown()
        await session_manager.shutdown()
        if bot.is_connected:
            await bot.stop()
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
