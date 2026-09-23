from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_examiner_pick_kb, admin_menu_kb, admin_post_pick_kb
from app.locales.i18n import t
from app.services.post_exam import (
    notify_admins_pick_examiner,
    send_post_exam_to_student,
)

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
    """Manual: re-trigger examiner pick (or send if already chosen)."""
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    booking = await repo.get_booking(session, booking_id)
    if not booking:
        await callback.answer("not found", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    examiners = await repo.list_active_examiners(session)
    if booking.speaking_examiner_id and booking.speaking_examiner:
        await send_post_exam_to_student(
            callback.bot,
            booking,
            settings,
            session,
            contact=booking.speaking_examiner.contact,
        )
        await callback.message.answer(
            t(user.lang, "admin_post_sent", id=booking.id),
            reply_markup=admin_menu_kb(user.lang),
        )
    elif examiners:
        # Reset prompt so admin can pick again
        booking.speaking_prompted = False
        await session.flush()
        await notify_admins_pick_examiner(callback.bot, booking, settings, session)
        await callback.message.answer(
            t(user.lang, "admin_post_pick_examiner"),
            reply_markup=admin_examiner_pick_kb(user.lang, booking.id, examiners),
        )
    else:
        await send_post_exam_to_student(
            callback.bot,
            booking,
            settings,
            session,
            contact=settings.speaking_contact,
        )
        await callback.message.answer(
            t(user.lang, "admin_post_sent", id=booking.id),
            reply_markup=admin_menu_kb(user.lang),
        )
    await callback.answer("OK")


@router.callback_query(F.data.startswith("adm:exam:"))
async def pick_examiner(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    # adm:exam:{booking_id}:{examiner_id}
    _, _, bid, eid = callback.data.split(":")
    booking = await repo.get_booking(session, int(bid))
    examiner = await repo.get_examiner(session, int(eid))
    if not booking or not examiner:
        await callback.answer("not found", show_alert=True)
        return
    booking = await repo.set_speaking_examiner(session, booking, examiner.id)
    await send_post_exam_to_student(
        callback.bot,
        booking,
        settings,
        session,
        contact=examiner.contact,
    )
    await callback.message.edit_text(
        (callback.message.text or "")
        + f"\n\n→ Speaking: {examiner.name} ({examiner.contact})"
    )
    await callback.answer("OK")
