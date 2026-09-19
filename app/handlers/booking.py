from datetime import date as date_cls

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callback_utils import safe_answer
from app.config import Settings
from app.db import repo
from app.db.models import SlotTime
from app.keyboards import (
    admin_price_assign_kb,
    cancel_kb,
    confirm_kb,
    dates_kb,
    main_menu_kb,
    slots_kb,
)
from app.locales.i18n import all_t, t
from app.states import BookingSG
from app.utils import format_dmY, h, normalize_full_name, parse_dmY

router = Router(name="booking")


@router.message(F.text.in_(all_t("btn_book")))
async def start_booking(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    user = await repo.get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    if not user.phone:
        from app.keyboards import phone_kb
        from app.states import OnboardingSG

        await state.set_state(OnboardingSG.phone)
        await message.answer(
            t(user.lang, "share_phone"), reply_markup=phone_kb(user.lang)
        )
        return
    await state.set_state(BookingSG.full_name)
    await message.answer(
        t(user.lang, "ask_full_name"), reply_markup=cancel_kb(user.lang)
    )


@router.message(BookingSG.full_name, F.text.in_(all_t("btn_cancel")))
@router.message(BookingSG.birth_date, F.text.in_(all_t("btn_cancel")))
async def cancel_booking_text(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    await state.clear()
    await message.answer(
        t(user.lang, "booking_cancelled"),
        reply_markup=main_menu_kb(user.lang, settings.is_admin(message.from_user.id)),
    )


@router.message(BookingSG.full_name)
async def booking_full_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    name = normalize_full_name(message.text or "")
    if not name:
        await message.answer(t(user.lang, "invalid_full_name"))
        return
    await state.update_data(full_name=name)
    await state.set_state(BookingSG.birth_date)
    await message.answer(t(user.lang, "ask_birth_date"))


@router.message(BookingSG.birth_date)
async def booking_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    birth = parse_dmY(message.text or "")
    if not birth:
        await message.answer(t(user.lang, "invalid_birth_date"))
        return
    await state.update_data(birth_date=birth.isoformat())
    dates = await repo.list_available_exam_dates(session)
    if not dates:
        await state.clear()
        await message.answer(
            t(user.lang, "no_dates"),
            reply_markup=main_menu_kb(
                user.lang, settings.is_admin(message.from_user.id)
            ),
        )
        return
    await state.set_state(BookingSG.exam_date)
    await message.answer(
        t(user.lang, "choose_date"), reply_markup=dates_kb(user.lang, dates)
    )


@router.callback_query(BookingSG.exam_date, F.data == "book:cancel")
@router.callback_query(BookingSG.slot, F.data == "book:cancel")
@router.callback_query(BookingSG.confirm, F.data == "book:cancel")
async def cancel_booking_cb(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(t(user.lang, "booking_cancelled"))
    await callback.message.answer(
        t(user.lang, "menu_title"),
        reply_markup=main_menu_kb(
            user.lang, settings.is_admin(callback.from_user.id)
        ),
    )


@router.callback_query(BookingSG.exam_date, F.data.startswith("book:date:"))
async def booking_pick_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    user = await repo.get_or_create_user(session, callback.from_user.id)
    exam_date_id = int(callback.data.split(":")[2])
    exam_date = await repo.get_exam_date(session, exam_date_id)
    if not exam_date or not await repo.is_date_available(session, exam_date):
        await safe_answer(callback, t(user.lang, "no_dates"), show_alert=True)
        return
    await state.update_data(exam_date_id=exam_date_id)
    await state.set_state(BookingSG.slot)
    await callback.message.edit_text(
        t(user.lang, "choose_slot"), reply_markup=slots_kb(user.lang)
    )


@router.callback_query(BookingSG.slot, F.data.startswith("book:slot:"))
async def booking_pick_slot(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    user = await repo.get_or_create_user(session, callback.from_user.id)
    slot_name = callback.data.split(":")[2]
    slot = SlotTime[slot_name]
    data = await state.get_data()
    exam_date = await repo.get_exam_date(session, int(data["exam_date_id"]))
    if not exam_date:
        await safe_answer(callback, t(user.lang, "no_dates"), show_alert=True)
        return
    await state.update_data(slot=slot.name)
    await state.set_state(BookingSG.confirm)
    text = t(
        user.lang,
        "confirm_booking",
        full_name=h(data["full_name"]),
        birth_date=h(format_dmY(date_cls.fromisoformat(data["birth_date"]))),
        exam_date=h(exam_date.exam_day.strftime("%d.%m.%Y")),
        slot=h(slot.value),
    )
    await callback.message.edit_text(text, reply_markup=confirm_kb(user.lang))


@router.callback_query(BookingSG.confirm, F.data == "book:confirm")
async def booking_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await repo.get_or_create_user(
        session, callback.from_user.id, callback.from_user.username
    )
    data = await state.get_data()
    exam_date = await repo.get_exam_date(session, int(data["exam_date_id"]))
    if not exam_date or not await repo.is_date_available(session, exam_date):
        await state.clear()
        await safe_answer(callback, t(user.lang, "no_dates"), show_alert=True)
        return

    booking = await repo.create_booking(
        session,
        user=user,
        exam_date=exam_date,
        full_name_en=data["full_name"],
        birth_date=date_cls.fromisoformat(data["birth_date"]),
        slot=SlotTime[data["slot"]],
    )
    await state.clear()
    await callback.message.edit_text(t(user.lang, "booking_submitted"))
    await callback.message.answer(
        t(user.lang, "menu_title"),
        reply_markup=main_menu_kb(
            user.lang, settings.is_admin(callback.from_user.id)
        ),
    )

    app_settings = await repo.ensure_app_settings(session)
    card = t(
        "ru",
        "admin_app_card",
        id=booking.id,
        full_name=h(booking.full_name_en),
        birth_date=h(format_dmY(booking.birth_date)),
        phone=h(user.phone or "—"),
        username=h(user.username or "—"),
        exam_date=h(exam_date.exam_day.strftime("%d.%m.%Y")),
        slot=h(booking.slot.value),
        status=h(booking.status.value),
        price="—",
    )
    for admin_id in settings.admin_id_list:
        try:
            await callback.bot.send_message(
                admin_id,
                f"{t('ru', 'new_app_notify')}\n\n{card}",
                reply_markup=admin_price_assign_kb(
                    "ru",
                    booking.id,
                    app_settings.price_own,
                    app_settings.price_new,
                ),
            )
        except Exception:
            pass
