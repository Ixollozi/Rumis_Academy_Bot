from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_menu_kb, language_kb
from app.locales.i18n import all_t, t
from app.states import OnboardingSG

router = Router(name="menu")


async def _user(session: AsyncSession, message: Message):
    return await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )


@router.message(F.text.in_(all_t("btn_change_lang")))
async def change_lang_btn(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await _user(session, message)
    await state.set_state(OnboardingSG.language)
    await state.update_data(change_lang_only=bool(user.phone))
    await message.answer(t(user.lang, "choose_language"), reply_markup=language_kb())


@router.message(F.text.in_(all_t("btn_admin")))
async def open_admin(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    user = await _user(session, message)
    if not settings.is_admin(message.from_user.id):
        await message.answer(t(user.lang, "admin_only"))
        return
    await message.answer(
        t(user.lang, "admin_menu"), reply_markup=admin_menu_kb(user.lang)
    )
