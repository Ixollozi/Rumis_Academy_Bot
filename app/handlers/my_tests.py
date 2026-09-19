from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import BookingStatus
from app.locales.i18n import all_t, t
from app.utils import format_price

router = Router(name="my_tests")


def _status_label(lang: str, status: BookingStatus) -> str:
    return t(lang, f"status_{status.value}")


@router.message(F.text.in_(all_t("btn_my_tests")))
async def my_tests(message: Message, session: AsyncSession) -> None:
    user = await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    bookings = await repo.list_user_bookings(session, user.id)
    if not bookings:
        await message.answer(t(user.lang, "my_tests_empty"))
        return
    chunks = []
    for b in bookings:
        chunks.append(
            t(
                user.lang,
                "my_test_item",
                id=b.id,
                exam_date=b.exam_date.exam_day.strftime("%d.%m.%Y"),
                slot=b.slot.value,
                status=_status_label(user.lang, b.status),
                price=format_price(b.price),
            )
        )
    await message.answer("\n\n".join(chunks))
