from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import (
    AppSettings,
    Booking,
    BookingStatus,
    ExamDate,
    SlotTime,
    User,
)

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


async def is_date_available(session: AsyncSession, exam_date: ExamDate) -> bool:
    if exam_date.is_closed:
        return False
    if exam_date.exam_day < date.today():
        return False
    paid = await paid_count_for_date(session, exam_date.id)
    return paid < exam_date.seat_limit


async def list_available_exam_dates(session: AsyncSession) -> list[ExamDate]:
    result = await session.execute(
        select(ExamDate)
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
    return [d for d in dates if paid_map.get(d.id, 0) < d.seat_limit]


async def list_all_exam_dates(session: AsyncSession) -> list[ExamDate]:
    result = await session.execute(select(ExamDate).order_by(ExamDate.exam_day.desc()))
    return list(result.scalars().all())


async def get_exam_date(session: AsyncSession, exam_date_id: int) -> ExamDate | None:
    return await session.get(ExamDate, exam_date_id)


async def create_exam_date(
    session: AsyncSession,
    exam_day: date,
    seat_limit: int | None = None,
) -> ExamDate:
    existing = await session.execute(
        select(ExamDate).where(ExamDate.exam_day == exam_day)
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
    slot: SlotTime,
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
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .where(Booking.id == booking.id)
    )
    return result.scalar_one()


async def get_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
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


async def mark_payment_review(session: AsyncSession, booking: Booking) -> Booking:
    booking.status = BookingStatus.payment_review
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


async def set_booking_result(
    session: AsyncSession, booking: Booking, result_text: str
) -> Booking:
    booking.result_text = result_text
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


async def mark_post_exam_sent(session: AsyncSession, booking: Booking) -> Booking:
    booking.post_exam_sent = True
    await session.flush()
    return await get_booking(session, booking.id)  # type: ignore[return-value]


def slot_datetime(exam_day: date, slot: SlotTime, tz_name: str) -> datetime:
    hour, minute = map(int, slot.value.split(":"))
    tz = ZoneInfo(tz_name)
    return datetime.combine(exam_day, time(hour=hour, minute=minute), tzinfo=tz)


def post_exam_due_at(exam_day: date, slot: SlotTime, tz_name: str) -> datetime:
    return slot_datetime(exam_day, slot, tz_name) + timedelta(hours=2, minutes=50)


async def list_paid_needing_post_exam(session: AsyncSession) -> list[Booking]:
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .where(
            Booking.status == BookingStatus.paid,
            Booking.post_exam_sent.is_(False),
        )
    )
    return list(result.scalars().all())


def bookings_export_query() -> Select[tuple[Booking]]:
    return (
        select(Booking)
        .options(selectinload(Booking.user), selectinload(Booking.exam_date))
        .order_by(Booking.created_at.desc())
    )
