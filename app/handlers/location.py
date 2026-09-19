from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.locales.i18n import all_t, t
from app.utils import h

router = Router(name="location")


@router.message(F.text.in_(all_t("btn_location")))
async def location(message: Message, session: AsyncSession, settings: Settings) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    maps = settings.maps_url or "—"
    await message.answer(
        t(
            user.lang,
            "location_text",
            center=h(settings.center_name),
            address=h(settings.center_address or "—"),
            phone=h(settings.center_phone or "—"),
            maps=h(maps),
        )
    )
    if settings.location_lat is not None and settings.location_lon is not None:
        await message.answer_location(
            latitude=settings.location_lat, longitude=settings.location_lon
        )


@router.message(F.text.in_(all_t("btn_contact_admin")))
async def contact_admin(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    await message.answer(
        t(
            user.lang,
            "contact_admin",
            admin_tg=h(settings.admin_telegram or "—"),
            phone=h(settings.center_phone or "—"),
        )
    )
