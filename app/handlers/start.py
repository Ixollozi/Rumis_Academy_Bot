from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import language_kb, main_menu_kb, phone_kb
from app.locales.i18n import t
from app.states import OnboardingSG

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    if user.phone:
        await state.clear()
        await message.answer(
            t(user.lang, "menu_title"),
            reply_markup=main_menu_kb(user.lang, settings.is_admin(message.from_user.id)),
        )
        return
    await state.clear()
    await state.set_state(OnboardingSG.language)
    await message.answer(t("ru", "choose_language"), reply_markup=language_kb())


@router.callback_query(OnboardingSG.language, F.data.startswith("lang:"))
async def onboarding_lang(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    lang = callback.data.split(":")[1]
    user = await repo.get_or_create_user(
        session, callback.from_user.id, callback.from_user.username
    )
    await repo.set_user_lang(session, user, lang)
    data = await state.get_data()

    if user.phone or data.get("change_lang_only"):
        await state.clear()
        await callback.message.edit_text(t(lang, "lang_changed"))
        await callback.message.answer(
            t(lang, "menu_title"),
            reply_markup=main_menu_kb(lang, settings.is_admin(callback.from_user.id)),
        )
        return

    await state.set_state(OnboardingSG.phone)
    # One message only: edit language prompt → confirmation, then ask phone once
    await callback.message.edit_text(t(lang, "lang_selected"))
    await callback.message.answer(
        t(lang, "share_phone"), reply_markup=phone_kb(lang)
    )


@router.message(OnboardingSG.phone, F.contact)
async def onboarding_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    contact = message.contact
    if not contact or (
        contact.user_id and contact.user_id != message.from_user.id
    ):
        user = await repo.get_or_create_user(session, message.from_user.id)
        await message.answer(t(user.lang, "need_phone"), reply_markup=phone_kb(user.lang))
        return
    user = await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = f"+{phone}"
    await repo.set_user_phone(session, user, phone)
    await state.clear()
    await message.answer(
        t(user.lang, "phone_saved"),
        reply_markup=main_menu_kb(user.lang, settings.is_admin(message.from_user.id)),
    )


@router.message(OnboardingSG.phone)
async def onboarding_phone_invalid(message: Message, session: AsyncSession) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    await message.answer(t(user.lang, "need_phone"), reply_markup=phone_kb(user.lang))
