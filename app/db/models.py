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


# All hours admin can attach to a date (9:00 … 23:00 + midnight 00:00)
ALL_SLOT_HOURS: tuple[str, ...] = tuple(
    f"{h:02d}:00" for h in range(9, 24)
) + ("00:00",)

DEFAULT_SLOT_HOURS: tuple[str, ...] = ("10:00", "13:00", "16:00")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(8), default="ru")
    # Linked Google Students sheet user id, e.g. user0117
    sheet_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    slots: Mapped[list[ExamSlot]] = relationship(
        back_populates="exam_date", cascade="all, delete-orphan"
    )


class ExamSlot(Base):
    __tablename__ = "exam_slots"
    __table_args__ = (
        UniqueConstraint("exam_date_id", "time_value", name="uq_exam_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_date_id: Mapped[int] = mapped_column(
        ForeignKey("exam_dates.id", ondelete="CASCADE"), index=True
    )
    time_value: Mapped[str] = mapped_column(String(8))  # "HH:MM"

    exam_date: Mapped[ExamDate] = relationship(back_populates="slots")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exam_date_id: Mapped[int] = mapped_column(
        ForeignKey("exam_dates.id", ondelete="CASCADE")
    )
    full_name_en: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date] = mapped_column(Date)
    # Wall-clock slot "HH:MM" (was SlotTime enum)
    slot: Mapped[str] = mapped_column(String(8), default="10:00")
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, length=32),
        default=BookingStatus.pending_price,
        index=True,
    )
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_exam_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    speaking_prompted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Payment receipt photo/document from student
    payment_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payment_file_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Speaking examiner chosen by admin after Main Test
    speaking_examiner_id: Mapped[int | None] = mapped_column(
        ForeignKey("speaking_examiners.id", ondelete="SET NULL"), nullable=True
    )
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
    speaking_examiner: Mapped[SpeakingExaminer | None] = relationship(
        back_populates="bookings"
    )


class SpeakingExaminer(Base):
    __tablename__ = "speaking_examiners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(200))  # @username or phone
    teacher_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # TCH001
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bookings: Mapped[list[Booking]] = relationship(back_populates="speaking_examiner")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_own: Mapped[int] = mapped_column(Integer, default=75_000)
    price_new: Mapped[int] = mapped_column(Integer, default=150_000)


class BotAdmin(Base):
    """Admins managed in bot UI. Env ADMIN_IDS are synced as is_owner=True."""

    __tablename__ = "bot_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
