from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.db.models import BookingStatus
from app.keyboards import admin_menu_kb, admin_result_pick_kb
from app.locales.i18n import t
from app.states import AdminSG

router = Router(name="admin_results")


@router.callback_query(F.data == "adm:results")
async def results_menu(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    bookings = await repo.list_bookings_by_statuses(session, [BookingStatus.paid])
    ids = [b.id for b in bookings]
    user = await repo.get_or_create_user(session, callback.from_user.id)
    if not ids:
        await callback.message.edit_text(
            t(user.lang, "admin_no_apps"), reply_markup=admin_menu_kb(user.lang)
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        t(user.lang, "admin_pick_result"),
        reply_markup=admin_result_pick_kb(user.lang, ids[:30]),
    )
    await callback.answer()


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
    await message.answer(
        t(user.lang, "admin_result_saved"), reply_markup=admin_menu_kb(user.lang)
    )
