from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_menu_kb
from app.locales.i18n import t
from app.states import AdminSG
from app.utils import format_price

router = Router(name="admin_prices")


@router.callback_query(F.data == "adm:prices")
async def prices_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    app_settings = await repo.ensure_app_settings(session)
    await state.set_state(AdminSG.set_prices)
    await callback.message.answer(
        t(
            user.lang,
            "admin_prices_now",
            own=format_price(app_settings.price_own),
            new=format_price(app_settings.price_new),
        )
    )
    await callback.answer()


@router.message(AdminSG.set_prices)
async def prices_save(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    user = await repo.get_or_create_user(session, message.from_user.id)
    parts = (message.text or "").replace(",", " ").split()
    if len(parts) != 2:
        await message.answer("Format: 75000 150000")
        return
    try:
        own, new = int(parts[0]), int(parts[1])
    except ValueError:
        await message.answer("Format: 75000 150000")
        return
    await repo.update_prices(session, own, new)
    await state.clear()
    await message.answer(
        t(user.lang, "admin_prices_saved", own=format_price(own), new=format_price(new)),
        reply_markup=admin_menu_kb(user.lang),
    )
