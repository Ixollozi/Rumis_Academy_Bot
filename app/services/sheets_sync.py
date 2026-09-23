"""
Google Sheets sync for IELTS_Coordinator_MASTER (Students / Results / Session Log).

Requires:
  GOOGLE_SHEETS_ID=...
  GOOGLE_CREDENTIALS_JSON=/path/to/service_account.json
and share the sheet with the service account email.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.db.models import Booking

logger = logging.getLogger(__name__)

STUDENTS_SHEET = "👥 Students"
RESULTS_SHEET = "📊 Results"
SESSION_SHEET = "📅 Session Log"


@lru_cache
def _client(credentials_path: str):
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    return gspread.authorize(creds)


def _enabled(settings: Settings) -> bool:
    path = (settings.google_credentials_json or "").strip()
    sid = (settings.google_sheets_id or "").strip()
    return bool(path and sid and Path(path).exists())


def _open(settings: Settings):
    return _client(settings.google_credentials_json).open_by_key(settings.google_sheets_id)


def _next_user_id(ws) -> str:
    """Scan column B for user0xxx and return next."""
    col = ws.col_values(2)  # User ID
    max_n = 0
    for cell in col:
        m = re.search(r"user0*(\d+)", str(cell), re.I)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"user{max_n + 1:04d}"


def _find_row_by_user(ws, user_id: str) -> int | None:
    col = ws.col_values(2)
    for i, v in enumerate(col, start=1):
        if str(v).strip().lower() == user_id.lower():
            return i
    return None


async def on_booking_paid(
    session: AsyncSession, booking: Booking, settings: Settings
) -> None:
    if not _enabled(settings):
        logger.info("Sheets sync skipped (not configured)")
        return
    try:
        sh = _open(settings)
        students = sh.worksheet(STUDENTS_SHEET)
        sessions = sh.worksheet(SESSION_SHEET)
        results = sh.worksheet(RESULTS_SHEET)

        user = booking.user
        sheet_uid = user.sheet_user_id
        if not sheet_uid:
            # New student → Students sheet
            sheet_uid = _next_user_id(students)
            # Find first empty row after header (row 1-2 headers)
            values = students.get_all_values()
            next_row = len(values) + 1
            no = next_row - 2 if next_row > 2 else 1
            students.update(
                f"A{next_row}:G{next_row}",
                [
                    [
                        no,
                        sheet_uid,
                        booking.full_name_en,
                        booking.birth_date.strftime("%d/%m/%Y"),
                        user.phone or "",
                        f"@{user.username}" if user.username else "",
                        booking.exam_date.exam_day.strftime("%d/%m/%Y"),
                    ]
                ],
            )
            user.sheet_user_id = sheet_uid
            await session.flush()
        else:
            # Returning — still log session; do not re-add to Students
            pass

        # Session Log append
        svals = sessions.get_all_values()
        srow = len(svals) + 1
        examiner_code = ""
        if booking.speaking_examiner and booking.speaking_examiner.teacher_code:
            examiner_code = booking.speaking_examiner.teacher_code
        sessions.update(
            f"A{srow}:G{srow}",
            [
                [
                    booking.exam_date.exam_day.strftime("%d/%m/%Y"),
                    booking.slot,
                    sheet_uid,
                    booking.full_name_en,
                    examiner_code,
                    "",  # Attendance
                    "Paid" if booking.price else "",
                ]
            ],
        )

        # Results stub row if missing
        if not _find_row_by_user(results, sheet_uid) or True:
            # Always append a result row per attempt
            rvals = results.get_all_values()
            rrow = len(rvals) + 1
            results.update(
                f"A{rrow}:D{rrow}",
                [
                    [
                        sheet_uid,
                        booking.full_name_en,
                        booking.exam_date.exam_day.strftime("%d/%m/%Y"),
                        booking.result_text or "",
                    ]
                ],
            )
        logger.info("Sheets synced paid booking #%s → %s", booking.id, sheet_uid)
    except Exception:
        logger.exception("Sheets on_booking_paid failed")


async def on_result_saved(
    session: AsyncSession, booking: Booking, settings: Settings
) -> None:
    if not _enabled(settings):
        return
    try:
        sh = _open(settings)
        results = sh.worksheet(RESULTS_SHEET)
        uid = booking.user.sheet_user_id or ""
        exam = booking.exam_date.exam_day.strftime("%d/%m/%Y")
        # Update matching row or append
        all_rows = results.get_all_values()
        updated = False
        for i, row in enumerate(all_rows, start=1):
            if len(row) >= 3 and row[0] == uid and row[2] == exam:
                results.update_cell(i, 4, booking.result_text or "")
                updated = True
                break
        if not updated:
            rrow = len(all_rows) + 1
            results.update(
                f"A{rrow}:D{rrow}",
                [[uid, booking.full_name_en, exam, booking.result_text or ""]],
            )
    except Exception:
        logger.exception("Sheets on_result_saved failed")


async def on_post_exam(
    session: AsyncSession, booking: Booking, settings: Settings
) -> None:
    """Fill Speaking Teacher ID in Session Log when examiner chosen."""
    if not _enabled(settings):
        return
    try:
        sh = _open(settings)
        sessions = sh.worksheet(SESSION_SHEET)
        uid = booking.user.sheet_user_id or ""
        exam = booking.exam_date.exam_day.strftime("%d/%m/%Y")
        code = ""
        if booking.speaking_examiner:
            code = booking.speaking_examiner.teacher_code or booking.speaking_examiner.contact
        rows = sessions.get_all_values()
        for i, row in enumerate(rows, start=1):
            if (
                len(row) >= 4
                and row[0] == exam
                and row[1] == booking.slot
                and row[2] == uid
            ):
                sessions.update_cell(i, 5, code)  # Speaking Teacher ID
                break
    except Exception:
        logger.exception("Sheets on_post_exam failed")
