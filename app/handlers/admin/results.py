from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import (
    admin_menu_kb,
    admin_result_pick_kb,
    admin_result_view_kb,
    admin_results_menu_kb,
)
from app.locales.i18n import t
from app.states import AdminSG
from app.utils import h

router = Router(name="admin_results")


@router.callback_query(F.data == "adm:results")
async def results_menu(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_results_menu"),
        reply_markup=admin_results_menu_kb(user.lang),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:results:pending")
async def results_pending(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    bookings = await repo.list_paid_awaiting_result(session)
    if not bookings:
        await callback.message.edit_text(
            t(user.lang, "admin_results_pending_empty"),
            reply_markup=admin_results_menu_kb(user.lang),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        t(user.lang, "admin_pick_result"),
        reply_markup=admin_result_pick_kb(user.lang, bookings[:40], archive=False),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:results:archive")
async def results_archive(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    bookings = await repo.list_paid_with_result(session)
    if not bookings:
        await callback.message.edit_text(
            t(user.lang, "admin_results_archive_empty"),
            reply_markup=admin_results_menu_kb(user.lang),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        t(user.lang, "admin_results_archive_pick"),
        reply_markup=admin_result_pick_kb(user.lang, bookings[:40], archive=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:resview:"))
async def result_view(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    booking = await repo.get_booking(session, booking_id)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    if not booking or not booking.result_text:
        await callback.answer(t(user.lang, "admin_no_apps"), show_alert=True)
        return
    day = booking.exam_date.exam_day.strftime("%d.%m.%Y")
    text = t(
        user.lang,
        "admin_results_archive_item",
        id=booking.id,
        name=h(booking.full_name_en),
        date=day,
        result=h(booking.result_text),
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_result_view_kb(user.lang, booking.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:resend:"))
async def result_resend(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    booking = await repo.get_booking(session, booking_id)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    if not booking or not booking.result_text:
        await callback.answer(t(user.lang, "admin_no_apps"), show_alert=True)
        return
    await callback.bot.send_message(
        booking.user.tg_id,
        t(
            booking.user.lang,
            "result_ready",
            exam_date=booking.exam_date.exam_day.strftime("%d.%m.%Y"),
            result=booking.result_text,
        ),
    )
    await callback.answer(t(user.lang, "admin_results_resent"), show_alert=True)


@router.callback_query(F.data.startswith("adm:res:"))
async def result_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.set_state(AdminSG.set_result)
    await state.update_data(booking_id=booking_id)
    await callback.message.answer(t(user.lang, "admin_ask_result", id=booking_id))
    await callback.answer()


@router.message(AdminSG.set_result)
async def result_save(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    booking = await repo.get_booking(session, int(data["booking_id"]))
    if not booking:
        await message.answer("Not found")
        await state.clear()
        return
    text = (message.text or "").strip()
    booking = await repo.set_booking_result(session, booking, text)
    await state.clear()
    user = await repo.get_or_create_user(session, message.from_user.id)
    await message.bot.send_message(
        booking.user.tg_id,
        t(
            booking.user.lang,
            "result_ready",
            exam_date=booking.exam_date.exam_day.strftime("%d.%m.%Y"),
            result=text,
        ),
    )
    try:
        from app.services import sheets_sync

        await sheets_sync.on_result_saved(session, booking, settings)
    except Exception:
        pass
    await message.answer(
        t(user.lang, "admin_result_saved"), reply_markup=admin_menu_kb(user.lang)
    )
