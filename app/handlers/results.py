from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import BookingStatus
from app.locales.i18n import all_t, t

router = Router(name="results")


@router.message(F.text.in_(all_t("btn_results")))
async def results(message: Message, session: AsyncSession) -> None:
    user = await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    bookings = await repo.list_user_bookings(session, user.id)
    paid = [b for b in bookings if b.status == BookingStatus.paid]
    if not paid:
        await message.answer(t(user.lang, "results_empty"))
        return
    parts = []
    for b in paid:
        exam = b.exam_date.exam_day.strftime("%d.%m.%Y")
        if b.result_text:
            parts.append(
                t(user.lang, "result_ready", exam_date=exam, result=b.result_text)
            )
        else:
            parts.append(f"{exam}: {t(user.lang, 'result_pending')}")
    await message.answer("\n\n".join(parts))
