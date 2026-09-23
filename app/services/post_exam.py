from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_session_factory, repo
from app.db.models import Booking
from app.keyboards import admin_examiner_pick_kb
from app.locales.i18n import t
from app.services import sheets_sync
from app.services.slots import post_exam_due

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def notify_admins_pick_examiner(
    bot: Bot, booking: Booking, settings: Settings, session: AsyncSession
) -> None:
    examiners = await repo.list_active_examiners(session)
    if not examiners:
        await send_post_exam_to_student(
            bot, booking, settings, session, contact=settings.speaking_contact
        )
        return

    card = (
        f"Student: {booking.full_name_en}\n"
        f"Test: Main Test\n"
        f"Session: {booking.slot}\n"
        f"Date: {booking.exam_date.exam_day.strftime('%d.%m.%Y')}\n\n"
        f"Who will conduct Speaking?"
    )
    kb = admin_examiner_pick_kb("ru", booking.id, examiners)
    for admin_id in settings.admin_id_list:
        try:
            await bot.send_message(admin_id, card, reply_markup=kb)
        except Exception:
            logger.exception("Failed examiner notify to %s", admin_id)
    await repo.mark_speaking_prompted(session, booking)


async def send_post_exam_to_student(
    bot: Bot,
    booking: Booking,
    settings: Settings,
    session: AsyncSession,
    *,
    contact: str | None,
) -> None:
    if booking.post_exam_sent:
        return
    lang = booking.user.lang or "ru"
    speaking = contact or settings.speaking_contact or "—"
    await bot.send_message(
        booking.user.tg_id,
        t(lang, "post_exam_speaking", speaking=speaking),
    )
    await bot.send_message(
        booking.user.tg_id,
        t(
            lang,
            "post_exam_channel",
            channel=settings.mock_channel,
            bot_username=settings.bot_username or "@CDI_Rumis_Bot",
        ),
    )
    await repo.mark_post_exam_sent(session, booking)
    try:
        await sheets_sync.on_post_exam(session, booking, settings)
    except Exception:
        logger.exception("Sheets sync after post-exam failed")


async def process_due_post_exams(bot: Bot, settings: Settings) -> None:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        now = datetime.now(ZoneInfo(settings.timezone))
        # 1) Prompt admins for examiner
        for booking in await repo.list_paid_needing_speaking_prompt(session):
            due = post_exam_due(
                booking.exam_date.exam_day, booking.slot, settings.timezone
            )
            if now >= due:
                try:
                    await notify_admins_pick_examiner(bot, booking, settings, session)
                except Exception:
                    logger.exception("Failed prompt for booking %s", booking.id)
        # 2) If examiner chosen but messages not sent
        for booking in await repo.list_paid_needing_post_exam(session):
            if not booking.speaking_examiner_id or booking.post_exam_sent:
                continue
            try:
                ex = booking.speaking_examiner
                contact = ex.contact if ex else settings.speaking_contact
                await send_post_exam_to_student(
                    bot, booking, settings, session, contact=contact
                )
            except Exception:
                logger.exception("Failed send for booking %s", booking.id)
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
