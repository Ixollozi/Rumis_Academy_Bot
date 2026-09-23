from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callback_utils import safe_answer
from app.config import Settings
from app.db import repo
from app.db.models import BookingStatus
from app.keyboards import (
    admin_apps_filter_kb,
    admin_menu_kb,
    admin_payment_kb,
    admin_price_assign_kb,
    paid_kb,
)
from app.locales.i18n import t
from app.services import sheets_sync
from app.states import PaymentSG
from app.utils import format_dmY, format_price, h

router = Router(name="admin_applications")

STATUS_MAP = {
    "pending_price": BookingStatus.pending_price,
    "awaiting_payment": BookingStatus.awaiting_payment,
    "payment_review": BookingStatus.payment_review,
    "paid": BookingStatus.paid,
}


@router.callback_query(F.data == "adm:apps")
async def apps_menu(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_apps"), reply_markup=admin_apps_filter_kb(user.lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:apps:"))
async def apps_list(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    key = callback.data.split(":")[2]
    status = STATUS_MAP[key]
    user = await repo.get_or_create_user(session, callback.from_user.id)
    bookings = await repo.list_bookings_by_statuses(session, [status])
    if not bookings:
        await callback.message.edit_text(
            t(user.lang, "admin_no_apps"),
            reply_markup=admin_apps_filter_kb(user.lang),
        )
        await callback.answer()
        return
    app_settings = await repo.ensure_app_settings(session)
    await callback.message.edit_text(f"{t(user.lang, 'admin_apps')}: {key}")
    for b in bookings[:20]:
        card = t(
            user.lang,
            "admin_app_card",
            id=b.id,
            full_name=b.full_name_en,
            birth_date=format_dmY(b.birth_date),
            phone=b.user.phone or "—",
            username=b.user.username or "—",
            exam_date=b.exam_date.exam_day.strftime("%d.%m.%Y"),
            slot=b.slot,
            status=b.status.value,
            price=format_price(b.price),
        )
        kb = None
        if b.status == BookingStatus.pending_price:
            kb = admin_price_assign_kb(
                user.lang, b.id, app_settings.price_own, app_settings.price_new
            )
        elif b.status == BookingStatus.payment_review:
            kb = admin_payment_kb(user.lang, b.id)
        await callback.message.answer(card, reply_markup=kb)
        if b.payment_file_id:
            try:
                if b.payment_file_type == "document":
                    await callback.message.answer_document(b.payment_file_id)
                else:
                    await callback.message.answer_photo(b.payment_file_id)
            except Exception:
                pass
    await callback.message.answer("—", reply_markup=admin_menu_kb(user.lang))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:price:"))
async def assign_price(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    _, _, booking_id_s, price_s = callback.data.split(":")
    booking = await repo.get_booking(session, int(booking_id_s))
    if not booking:
        await callback.answer("not found", show_alert=True)
        return
    booking = await repo.set_booking_price(
        booking=booking, session=session, price=int(price_s)
    )
    lang = booking.user.lang
    await callback.message.edit_text(
        callback.message.text + f"\n\n→ price {price_s}"
    )
    await callback.bot.send_message(
        booking.user.tg_id,
        t(
            lang,
            "price_assigned",
            price=format_price(booking.price),
            payment_details=settings.payment_details or "—",
        ),
        reply_markup=paid_kb(lang, booking.id),
    )
    await callback.answer("OK")


@router.callback_query(F.data.startswith("adm:reject:"))
async def reject_app(
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
    booking = await repo.reject_booking(session, booking)
    await callback.bot.send_message(
        booking.user.tg_id, t(booking.user.lang, "payment_rejected")
    )
    await callback.message.edit_text(callback.message.text + "\n\n→ rejected")
    await callback.answer("OK")


@router.callback_query(F.data.startswith("pay:done:"))
async def user_paid(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    booking_id = int(callback.data.split(":")[2])
    booking = await repo.get_booking(session, booking_id)
    if not booking or booking.user.tg_id != callback.from_user.id:
        await callback.answer("no", show_alert=True)
        return
    if booking.status not in (
        BookingStatus.awaiting_payment,
        BookingStatus.payment_review,
    ):
        await callback.answer("already processed", show_alert=True)
        return
    await state.set_state(PaymentSG.await_receipt)
    await state.update_data(booking_id=booking_id)
    await callback.message.edit_text(t(booking.user.lang, "ask_receipt"))
    await callback.answer()


async def _submit_receipt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    *,
    file_id: str,
    file_type: str,
    booking_id: int | None = None,
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    if booking_id is None:
        data = await state.get_data()
        booking_id = int(data.get("booking_id") or 0)
    booking = await repo.get_booking(session, booking_id) if booking_id else None
    if not booking or booking.user.tg_id != message.from_user.id:
        # try latest awaiting booking
        bookings = await repo.list_user_bookings(session, user.id)
        booking = next(
            (
                b
                for b in bookings
                if b.status == BookingStatus.awaiting_payment
            ),
            None,
        )
    if not booking or booking.status not in (
        BookingStatus.awaiting_payment,
        BookingStatus.payment_review,
    ):
        await message.answer(t(user.lang, "receipt_no_booking"))
        await state.clear()
        return

    booking = await repo.mark_payment_review(
        session, booking, file_id=file_id, file_type=file_type
    )
    await state.clear()
    await message.answer(t(user.lang, "payment_sent"))

    card = t(
        "ru",
        "admin_app_card",
        id=booking.id,
        full_name=booking.full_name_en,
        birth_date=format_dmY(booking.birth_date),
        phone=booking.user.phone or "—",
        username=booking.user.username or "—",
        exam_date=booking.exam_date.exam_day.strftime("%d.%m.%Y"),
        slot=booking.slot,
        status=booking.status.value,
        price=format_price(booking.price),
    )
    for admin_id in settings.admin_id_list:
        try:
            await message.bot.send_message(
                admin_id,
                f"{t('ru', 'payment_notify')}\n\n{card}",
                reply_markup=admin_payment_kb("ru", booking.id),
            )
            if file_type == "document":
                await message.bot.send_document(admin_id, file_id)
            else:
                await message.bot.send_photo(admin_id, file_id)
        except Exception:
            pass


@router.message(PaymentSG.await_receipt, F.photo)
async def receipt_photo(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    photo = message.photo[-1]
    await _submit_receipt(
        message,
        state,
        session,
        settings,
        file_id=photo.file_id,
        file_type="photo",
    )


@router.message(PaymentSG.await_receipt, F.document)
async def receipt_doc(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    await _submit_receipt(
        message,
        state,
        session,
        settings,
        file_id=message.document.file_id,
        file_type="document",
    )


@router.message(PaymentSG.await_receipt)
async def receipt_need_file(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await repo.get_or_create_user(session, message.from_user.id)
    await message.answer(t(user.lang, "ask_receipt"))


@router.callback_query(F.data.startswith("adm:paid:"))
async def mark_paid(
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
    admin = await repo.get_or_create_user(session, callback.from_user.id)
    updated = await repo.mark_paid(session, booking)
    if updated is None:
        paid = await repo.paid_count_for_date(session, booking.exam_date_id)
        await safe_answer(
            callback,
            t(
                admin.lang,
                "admin_limit_full",
                paid=paid,
                limit=booking.exam_date.seat_limit,
            ),
            show_alert=True,
        )
        return
    booking = updated
    await callback.bot.send_message(
        booking.user.tg_id,
        t(
            booking.user.lang,
            "payment_confirmed",
            exam_date=h(booking.exam_date.exam_day.strftime("%d.%m.%Y")),
            slot=h(booking.slot),
            address=h(settings.center_address or "—"),
        ),
    )
    await callback.message.edit_text(
        (callback.message.text or "") + f"\n\n→ {t(admin.lang, 'admin_mark_paid')}"
    )
    # Google Sheets sync (best-effort)
    try:
        await sheets_sync.on_booking_paid(session, booking, settings)
    except Exception:
        pass
    await callback.answer("OK")


@router.callback_query(F.data.startswith("adm:unpay:"))
async def unpay(
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
    booking = await repo.mark_payment_rejected(session, booking)
    await callback.bot.send_message(
        booking.user.tg_id, t(booking.user.lang, "payment_rejected")
    )
    await callback.message.edit_text(callback.message.text + "\n\n→ payment rejected")
    await callback.answer("OK")
