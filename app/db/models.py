from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BookingStatus(str, enum.Enum):
    pending_price = "pending_price"
    awaiting_payment = "awaiting_payment"
    payment_review = "payment_review"
    paid = "paid"
    rejected = "rejected"
    cancelled = "cancelled"


class SlotTime(str, enum.Enum):
    s10 = "10:00"
    s13 = "13:00"
    s16 = "16:00"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(8), default="ru")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bookings: Mapped[list[Booking]] = relationship(back_populates="user")


class ExamDate(Base):
    __tablename__ = "exam_dates"
    __table_args__ = (UniqueConstraint("exam_day", name="uq_exam_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day: Mapped[date] = mapped_column(Date, index=True)
    seat_limit: Mapped[int] = mapped_column(Integer, default=10)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bookings: Mapped[list[Booking]] = relationship(back_populates="exam_date")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exam_date_id: Mapped[int] = mapped_column(
        ForeignKey("exam_dates.id", ondelete="CASCADE")
    )
    full_name_en: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date] = mapped_column(Date)
    slot: Mapped[SlotTime] = mapped_column(
        Enum(SlotTime, name="slot_time", native_enum=False, length=16)
    )
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, length=32),
        default=BookingStatus.pending_price,
        index=True,
    )
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_exam_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="bookings")
    exam_date: Mapped[ExamDate] = relationship(back_populates="bookings")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_own: Mapped[int] = mapped_column(Integer, default=75_000)
    price_new: Mapped[int] = mapped_column(Integer, default=150_000)
