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
    maps = settings.maps_url or (
        "https://maps.google.com/maps?q=41.364602,69.273439"
        "&ll=41.364602,69.273439&z=16"
    )
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
    lat = settings.location_lat if settings.location_lat is not None else 41.364602
    lon = settings.location_lon if settings.location_lon is not None else 69.273439
    try:
        await message.answer_venue(
            latitude=lat,
            longitude=lon,
            title=settings.center_name or "Rumis Academy",
            address=settings.center_address or "Майкурган 26/2",
        )
    except Exception:
        await message.answer_location(latitude=lat, longitude=lon)


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
