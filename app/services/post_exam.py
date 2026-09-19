from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_session_factory
from app.db import repo
from app.db.models import Booking
from app.locales.i18n import t

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def send_post_exam_messages(
    bot: Bot, booking: Booking, settings: Settings, session: AsyncSession
) -> None:
    if booking.post_exam_sent:
        return
    lang = booking.user.lang or "ru"
    await bot.send_message(
        booking.user.tg_id,
        t(
            lang,
            "post_exam_speaking",
            speaking=settings.speaking_contact or "—",
        ),
    )
    await bot.send_message(
        booking.user.tg_id,
        t(lang, "post_exam_channel", channel=settings.mock_channel),
    )
    await repo.mark_post_exam_sent(session, booking)


async def process_due_post_exams(bot: Bot, settings: Settings) -> None:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        bookings = await repo.list_paid_needing_post_exam(session)
        now = datetime.now(ZoneInfo(settings.timezone))
        for booking in bookings:
            due = repo.post_exam_due_at(
                booking.exam_date.exam_day, booking.slot, settings.timezone
            )
            if now >= due:
                try:
                    await send_post_exam_messages(bot, booking, settings, session)
                except Exception:
                    logger.exception("Failed post-exam for booking %s", booking.id)
        await session.commit()


def start_scheduler(bot: Bot, settings: Settings) -> AsyncIOScheduler:
    if not scheduler.running:
        scheduler.add_job(
            process_due_post_exams,
            "interval",
            minutes=1,
            args=[bot, settings],
            id="post_exam_poll",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Post-exam scheduler started")
    return scheduler
