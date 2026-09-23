from __future__ import annotations

from aiogram import Bot
from aiogram.types import FSInputFile
from openpyxl import Workbook
from pathlib import Path
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Booking
from app.utils import format_dmY, format_price


EXPORT_DIR = Path("exports")


def build_workbook(bookings: list[Booking]) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"rumis_bookings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Bookings"
    ws.append(
        [
            "ID",
            "Full name (EN)",
            "Birth date",
            "Phone",
            "Username",
            "Exam datetime",
            "Exam date",
            "Slot",
            "Price",
            "Status",
            "Registered at",
            "Result",
        ]
    )
    for b in bookings:
        exam_day = b.exam_date.exam_day.strftime("%d.%m.%Y")
        ws.append(
            [
                b.id,
                b.full_name_en,
                format_dmY(b.birth_date),
                b.user.phone or "",
                b.user.username or "",
                f"{exam_day} {b.slot}",
                exam_day,
                b.slot,
                format_price(b.price),
                b.status.value,
                b.created_at.strftime("%d.%m.%Y %H:%M") if b.created_at else "",
                b.result_text or "",
            ]
        )
    wb.save(path)
    return path


async def export_bookings_xlsx(session: AsyncSession) -> Path:
    bookings = await repo.list_all_bookings(session)
    return build_workbook(bookings)


async def send_excel(bot: Bot, chat_id: int, session: AsyncSession) -> None:
    path = await export_bookings_xlsx(session)
    await bot.send_document(chat_id, FSInputFile(path))
