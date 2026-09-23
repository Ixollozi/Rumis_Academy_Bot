from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import (
    DEFAULT_SLOT_HOURS,
    AppSettings,
    Booking,
    BookingStatus,
    BotAdmin,
    ExamDate,
    ExamSlot,
    SpeakingExaminer,
    User,
)
from app.services.slots import post_exam_due, slot_is_open, sort_slot_values

settings = get_settings()


async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user:
        if username and user.username != username:
            user.username = username
        return user
    user = User(tg_id=tg_id, username=username, lang="ru")
    session.add(user)
    await session.flush()
    return user


async def set_user_lang(session: AsyncSession, user: User, lang: str) -> User:
    user.lang = lang
    await session.flush()
    return user


async def set_user_phone(session: AsyncSession, user: User, phone: str) -> User:
    user.phone = phone
    await session.flush()
    return user


async def ensure_app_settings(session: AsyncSession) -> AppSettings:
    result = await session.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row:
        return row
    row = AppSettings(
        price_own=settings.default_price_own,
        price_new=settings.default_price_new,
    )
    session.add(row)
    await session.flush()
    return row


async def update_prices(
    session: AsyncSession, price_own: int, price_new: int
) -> AppSettings:
    row = await ensure_app_settings(session)
    row.price_own = price_own
    row.price_new = price_new
    await session.flush()
    return row


async def paid_count_for_date(session: AsyncSession, exam_date_id: int) -> int:
    result = await session.execute(
        select(func.count(Booking.id)).where(
            Booking.exam_date_id == exam_date_id,
            Booking.status == BookingStatus.paid,
        )
    )
    return int(result.scalar_one())


async def get_exam_slots(session: AsyncSession, exam_date_id: int) -> list[ExamSlot]:
    result = await session.execute(
        select(ExamSlot).where(ExamSlot.exam_date_id == exam_date_id)
    )
    slots = list(result.scalars().all())
    order = sort_slot_values([s.time_value for s in slots])
    by = {s.time_value: s for s in slots}
    return [by[v] for v in order if v in by]


async def list_open_slot_values(
    session: AsyncSession, exam_date: ExamDate, tz_name: str | None = None
) -> list[str]:
    """Slot times still bookable for this date (not started yet)."""
    tz = tz_name or settings.timezone
    slots = await get_exam_slots(session, exam_date.id)
    values = [s.time_value for s in slots]
    if not values:
        values = list(DEFAULT_SLOT_HOURS)
    return [v for v in sort_slot_values(values) if slot_is_open(exam_date.exam_day, v, tz)]


async def date_has_open_slots(
    session: AsyncSession, exam_date: ExamDate, tz_name: str | None = None
) -> bool:
    return bool(await list_open_slot_values(session, exam_date, tz_name))


async def is_date_available(session: AsyncSession, exam_date: ExamDate) -> bool:
    if exam_date.is_closed:
        return False
    if exam_date.exam_day < date.today():
        return False
    paid = await paid_count_for_date(session, exam_date.id)
    if paid >= exam_date.seat_limit:
        return False
    return await date_has_open_slots(session, exam_date)


async def list_available_exam_dates(session: AsyncSession) -> list[ExamDate]:
    result = await session.execute(
        select(ExamDate)
        .options(selectinload(ExamDate.slots))
        .where(ExamDate.is_closed.is_(False), ExamDate.exam_day >= date.today())
        .order_by(ExamDate.exam_day)
    )
    dates = list(result.scalars().all())
    if not dates:
        return []
    ids = [d.id for d in dates]
    counts_result = await session.execute(
        select(Booking.exam_date_id, func.count(Booking.id))
        .where(
            Booking.exam_date_id.in_(ids),
            Booking.status == BookingStatus.paid,
        )
        .group_by(Booking.exam_date_id)
    )
    paid_map = {row[0]: int(row[1]) for row in counts_result.all()}
    out: list[ExamDate] = []
    for d in dates:
        if paid_map.get(d.id, 0) >= d.seat_limit:
            continue
        if await date_has_open_slots(session, d):
            out.append(d)
    return out


async def list_all_exam_dates(session: AsyncSession) -> list[ExamDate]:
    result = await session.execute(
        select(ExamDate)
        .options(selectinload(ExamDate.slots))
        .order_by(ExamDate.exam_day.desc())
    )
    return list(result.scalars().all())


async def get_exam_date(session: AsyncSession, exam_date_id: int) -> ExamDate | None:
    result = await session.execute(
        select(ExamDate)
        .options(selectinload(ExamDate.slots))
        .where(ExamDate.id == exam_date_id)
    )
    return result.scalar_one_or_none()


async def create_exam_date(
    session: AsyncSession,
    exam_day: date,
    seat_limit: int | None = None,
) -> ExamDate:
    existing = await session.execute(
        select(ExamDate)
        .options(selectinload(ExamDate.slots))
        .where(ExamDate.exam_day == exam_day)
    )
    row = existing.scalar_one_or_none()
    if row:
        row.is_closed = False
        if seat_limit is not None:
            row.seat_limit = seat_limit
        await session.flush()
        return row
    row = ExamDate(
        exam_day=exam_day,
        seat_limit=seat_limit or settings.default_date_limit,
    )
    session.add(row)
    await session.flush()
    return row


async def set_exam_date_slots(
    session: AsyncSession, exam_date_id: int, time_values: list[str]
) -> ExamDate | None:
    exam = await get_exam_date(session, exam_date_id)
    if not exam:
        return None
    # delete old
    for s in list(exam.slots):
        await session.delete(s)
    await session.flush()
    for tv in sort_slot_values(list(set(time_values))):
        session.add(ExamSlot(exam_date_id=exam_date_id, time_value=tv))
    await session.flush()
    return await get_exam_date(session, exam_date_id)


async def ensure_default_slots_for_all(session: AsyncSession) -> None:
    """Dates without slots get 10/13/16 (migration helper)."""
    dates = await list_all_exam_dates(session)
    for d in dates:
        existing = await get_exam_slots(session, d.id)
        if existing:
            continue
        for tv in DEFAULT_SLOT_HOURS:
            session.add(ExamSlot(exam_date_id=d.id, time_value=tv))
    await session.flush()


async def set_exam_date_limit(
    session: AsyncSession, exam_date_id: int, seat_limit: int
) -> ExamDate | None:
    row = await session.get(ExamDate, exam_date_id)
    if not row:
        return None
    row.seat_limit = seat_limit
    await session.flush()
    return row


async def close_exam_date(session: AsyncSession, exam_date_id: int) -> ExamDate | None:
    row = await session.get(ExamDate, exam_date_id)
    if not row:
        return None
    row.is_closed = True
    await session.flush()
    return row


async def create_booking(
    session: AsyncSession,
    *,
    user: User,
    exam_date: ExamDate,
    full_name_en: str,
    birth_date: date,
    slot: str,
) -> Booking:
    booking = Booking(
        user_id=user.id,
        exam_date_id=exam_date.id,
        full_name_en=full_name_en,
        birth_date=birth_date,
        slot=slot,
        status=BookingStatus.pending_price,
    )
    session.add(booking)
    await session.flush()
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.exam_date),
            selectinload(Booking.speaking_examiner),
        )
        .where(Booking.id == booking.id)
    )
    return result.scalar_one()


async def get_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.exam_date),
            selectinload(Booking.speaking_examiner),
        )
        .where(Booking.id == booking_id)
    )
    return result.scalar_one_or_none()


async def set_booking_price(
    session: AsyncSession, booking: Booking, price: int
) -> Booking:
    booking.price = price
    booking.status = BookingStatus.awaiting_payment
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def reject_booking(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.rejected
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def mark_payment_review(
    session: AsyncSession,
    booking: Booking,
    *,
    file_id: str | None = None,
    file_type: str | None = None,
) -> Booking:
    booking.status = BookingStatus.payment_review
    if file_id:
        booking.payment_file_id = file_id
        booking.payment_file_type = file_type or "photo"
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def can_accept_paid(session: AsyncSession, exam_date: ExamDate) -> bool:
    paid = await paid_count_for_date(session, exam_date.id)
    return paid < exam_date.seat_limit


async def mark_paid(session: AsyncSession, booking: Booking) -> Booking | None:
    exam_date = booking.exam_date
    if exam_date is None:
        exam_date = await session.get(ExamDate, booking.exam_date_id)
    if exam_date is None:
        return None
    if not await can_accept_paid(session, exam_date):
        return None
    booking.status = BookingStatus.paid
    await session.flush()
    return await get_booking(session, booking.id)


async def mark_payment_rejected(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.rejected
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def list_user_bookings(session: AsyncSession, user_id: int) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.exam_date))
        .where(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
    )
    return list(result.scalars().all())


async def list_bookings_by_statuses(
    session: AsyncSession, statuses: list[BookingStatus]
) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .where(Booking.status.in_(statuses))
        .order_by(Booking.created_at.desc())
    )
    return list(result.scalars().all())


async def list_all_bookings(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .order_by(Booking.created_at.desc())
    )
    return list(result.scalars().all())


async def list_registered_users(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.phone.is_not(None), User.phone != "")
        .order_by(User.id)
    )
    return list(result.scalars().all())


async def list_users_with_paid(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User)
        .join(Booking, Booking.user_id == User.id)
        .where(Booking.status == BookingStatus.paid)
        .distinct()
        .order_by(User.id)
    )
    return list(result.scalars().all())


async def list_paid_awaiting_result(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .where(
            Booking.status == BookingStatus.paid,
            (Booking.result_text.is_(None)) | (Booking.result_text == ""),
        )
        .order_by(Booking.created_at.desc())
    )
    return list(result.scalars().all())


async def list_paid_with_result(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .where(
            Booking.status == BookingStatus.paid,
            Booking.result_text.is_not(None),
            Booking.result_text != "",
        )
        .order_by(Booking.updated_at.desc())
    )
    return list(result.scalars().all())


async def set_booking_result(
    session: AsyncSession, booking: Booking, result_text: str
) -> Booking:
    booking.result_text = result_text
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def mark_speaking_prompted(session: AsyncSession, booking: Booking) -> Booking:
    booking.speaking_prompted = True
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def mark_post_exam_sent(session: AsyncSession, booking: Booking) -> Booking:
    booking.post_exam_sent = True
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def set_speaking_examiner(
    session: AsyncSession, booking: Booking, examiner_id: int
) -> Booking:
    booking.speaking_examiner_id = examiner_id
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


def slot_datetime(exam_day: date, slot: str, tz_name: str) -> datetime:
    from app.services.slots import slot_start_dt

    return slot_start_dt(exam_day, slot, tz_name)


def post_exam_due_at(exam_day: date, slot: str, tz_name: str) -> datetime:
    return post_exam_due(exam_day, slot, tz_name)


async def list_paid_needing_post_exam(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.exam_date),
            selectinload(Booking.speaking_examiner),
        )
        .where(
            Booking.status == BookingStatus.paid,
            Booking.post_exam_sent.is_(False),
        )
    )
    return list(result.scalars().all())


async def list_paid_needing_speaking_prompt(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.exam_date),
            selectinload(Booking.speaking_examiner),
        )
        .where(
            Booking.status == BookingStatus.paid,
            Booking.post_exam_sent.is_(False),
            Booking.speaking_prompted.is_(False),
        )
    )
    return list(result.scalars().all())


def bookings_export_query() -> Select[tuple[Booking]]:
    return (
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .order_by(Booking.created_at.desc())
    )


# --- speaking examiners ---


async def list_active_examiners(session: AsyncSession) -> list[SpeakingExaminer]:
    result = await session.execute(
        select(SpeakingExaminer)
        .where(SpeakingExaminer.is_active.is_(True))
        .order_by(SpeakingExaminer.id)
    )
    return list(result.scalars().all())


async def list_all_examiners(session: AsyncSession) -> list[SpeakingExaminer]:
    result = await session.execute(
        select(SpeakingExaminer).order_by(SpeakingExaminer.id)
    )
    return list(result.scalars().all())


async def get_examiner(
    session: AsyncSession, examiner_id: int
) -> SpeakingExaminer | None:
    return await session.get(SpeakingExaminer, examiner_id)


async def add_examiner(
    session: AsyncSession,
    *,
    name: str,
    contact: str,
    teacher_code: str | None = None,
) -> SpeakingExaminer:
    row = SpeakingExaminer(
        name=name.strip(),
        contact=contact.strip(),
        teacher_code=teacher_code,
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def deactivate_examiner(session: AsyncSession, examiner_id: int) -> bool:
    row = await session.get(SpeakingExaminer, examiner_id)
    if not row:
        return False
    row.is_active = False
    await session.flush()
    return True


async def seed_examiners_from_contacts(
    session: AsyncSession, speaking_contact: str
) -> None:
    """If no examiners yet, seed from SPEAKING_CONTACT env (@a @b)."""
    existing = await list_all_examiners(session)
    if existing:
        return
    parts = [p.strip() for p in speaking_contact.replace(",", " ").split() if p.strip()]
    for i, p in enumerate(parts, start=1):
        name = p.lstrip("@")
        session.add(
            SpeakingExaminer(
                name=name,
                contact=p if p.startswith("@") else f"@{p}",
                teacher_code=f"TCH{i:03d}",
                is_active=True,
            )
        )
    await session.flush()


# --- bot admins (unchanged API) ---


async def list_bot_admins(session: AsyncSession) -> list[BotAdmin]:
    result = await session.execute(select(BotAdmin).order_by(BotAdmin.id))
    return list(result.scalars().all())


async def get_bot_admin(session: AsyncSession, tg_id: int) -> BotAdmin | None:
    result = await session.execute(select(BotAdmin).where(BotAdmin.tg_id == tg_id))
    return result.scalar_one_or_none()


async def sync_owner_admins(
    session: AsyncSession, owner_tg_ids: list[int]
) -> None:
    owners = set(owner_tg_ids)
    existing = await list_bot_admins(session)
    by_id = {a.tg_id: a for a in existing}
    for tg_id in owners:
        row = by_id.get(tg_id)
        if row:
            row.is_owner = True
        else:
            session.add(BotAdmin(tg_id=tg_id, is_owner=True))
    for row in existing:
        if row.is_owner and row.tg_id not in owners:
            row.is_owner = False
    await session.flush()


async def add_bot_admin(
    session: AsyncSession,
    tg_id: int,
    *,
    username: str | None = None,
    is_owner: bool = False,
) -> BotAdmin:
    row = await get_bot_admin(session, tg_id)
    if row:
        if username and row.username != username:
            row.username = username
        await session.flush()
        return row
    if not username:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        u = result.scalar_one_or_none()
        if u:
            username = u.username
    row = BotAdmin(tg_id=tg_id, username=username, is_owner=is_owner)
    session.add(row)
    await session.flush()
    return row


async def remove_bot_admin(session: AsyncSession, tg_id: int) -> str | None:
    row = await get_bot_admin(session, tg_id)
    if not row:
        return "not_found"
    if row.is_owner:
        return "is_owner"
    all_admins = await list_bot_admins(session)
    if len(all_admins) <= 1:
        return "last_admin"
    await session.delete(row)
    await session.flush()
    return None


async def count_bot_admins(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(BotAdmin.id)))
    return int(result.scalar_one())
