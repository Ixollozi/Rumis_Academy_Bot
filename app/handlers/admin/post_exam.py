from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_menu_kb, admin_post_pick_kb
from app.locales.i18n import t
from app.services.post_exam import send_post_exam_messages

router = Router(name="admin_post_exam")


@router.callback_query(F.data == "adm:post")
async def post_menu(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    bookings = await repo.list_paid_needing_post_exam(session)
    ids = [b.id for b in bookings]
    user = await repo.get_or_create_user(session, callback.from_user.id)
    if not ids:
        await callback.message.edit_text(
            t(user.lang, "admin_no_apps"), reply_markup=admin_menu_kb(user.lang)
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        t(user.lang, "admin_pick_post"),
        reply_markup=admin_post_pick_kb(user.lang, ids[:30]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:postsend:"))
async def post_send(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    booking = await repo.get_booking(session, booking_id)
    if not booking:
        await callback.answer("not found", show_alert=True)
        return
    await send_post_exam_messages(callback.bot, booking, settings, session)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.answer(
        t(user.lang, "admin_post_sent", id=booking.id),
        reply_markup=admin_menu_kb(user.lang),
    )
    await callback.answer("OK")
