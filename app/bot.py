import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings
from app.db import get_session_factory, init_db
from app.db import repo
from app.handlers import setup_routers
from app.middlewares import (
    DbSessionMiddleware,
    SettingsMiddleware,
    UpdateCallbackAnswerMiddleware,
)
from app.services.post_exam import start_scheduler
from app.services import admin_access


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token or settings.bot_token.endswith("REPLACE_ME"):
        logger.error("Set BOT_TOKEN in .env")
        sys.exit(1)

    await init_db()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await repo.ensure_app_settings(session)
        await repo.ensure_default_slots_for_all(session)
        await repo.seed_examiners_from_contacts(session, settings.speaking_contact)
        admins = await admin_access.sync_admins(session, settings.env_owner_ids)
        await session.commit()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    # Answer inline callbacks ASAP (removes Telegram loading spinner)
    dp.update.middleware(UpdateCallbackAnswerMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(SettingsMiddleware(settings))
    dp.include_router(setup_routers())

    start_scheduler(bot, settings)
    logger.info("Bot starting (admins=%s)", admins)
    await dp.start_polling(
        bot,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    asyncio.run(main())
