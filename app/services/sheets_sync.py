"""
Google Sheets sync for IELTS_Coordinator_MASTER (Students / Results / Session Log).

Writes by header names (typically row 4), not fixed A1:G ranges.

Requires:
  GOOGLE_SHEETS_ID=...
  GOOGLE_CREDENTIALS_JSON=/path/to/service_account.json
and share the sheet with the service account email.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Booking

logger = logging.getLogger(__name__)

STUDENTS_SHEET = "👥 Students"
RESULTS_SHEET = "📊 Results"
SESSION_SHEET = "📅 Session Log"

# Markers that identify a header row
_HEADER_MARKERS = ("Student ID", "Date", "Full Name", "Test Date")


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


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def find_header_row(values: list[list[str]]) -> tuple[int, dict[str, int]]:
    """
    Return 0-based row index and map of normalized header → 0-based col index.
    Prefers a row containing 'Student ID' or similar markers.
    """
    best_i = -1
    best_map: dict[str, int] = {}
    for i, row in enumerate(values[:30]):
        mapping: dict[str, int] = {}
        for j, cell in enumerate(row):
            key = _norm(str(cell))
            if key and key not in mapping:
                mapping[key] = j
        markers_hit = sum(1 for m in _HEADER_MARKERS if _norm(m) in mapping)
        if markers_hit >= 1 and (
            "student id" in mapping or "date" in mapping or "full name" in mapping
        ):
            if markers_hit > len(best_map) // 2 or best_i < 0:
                best_i = i
                best_map = mapping
                if "student id" in mapping:
                    break
    if best_i < 0:
        # Fallback: first non-empty row
        for i, row in enumerate(values[:10]):
            if any(str(c).strip() for c in row):
                mapping = {}
                for j, cell in enumerate(row):
                    key = _norm(str(cell))
                    if key and key not in mapping:
                        mapping[key] = j
                return i, mapping
        return 0, {}
    return best_i, best_map


def _col_letter(idx0: int) -> str:
    """0-based index → A, B, … Z, AA, …"""
    n = idx0 + 1
    letters = []
    while n:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _next_student_id(values: list[list[str]], header_idx: int, id_col: int | None) -> str:
    max_n = 0
    if id_col is None:
        return "user0001"
    for row in values[header_idx + 1 :]:
        if id_col >= len(row):
            continue
        m = re.search(r"user0*(\d+)", str(row[id_col]), re.I)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"user{max_n + 1:04d}"


def _ensure_header(
    ws, values: list[list[str]], header_idx: int, headers: dict[str, int], name: str
) -> tuple[list[list[str]], dict[str, int]]:
    """If header `name` missing, append it at end of header row (no mid-insert)."""
    key = _norm(name)
    if key in headers:
        return values, headers
    row_1based = header_idx + 1
    header_row = list(values[header_idx]) if header_idx < len(values) else []
    new_col = len(header_row)
    # Trim trailing empties for placement, but keep index = current width of used range
    while header_row and not str(header_row[-1]).strip():
        header_row.pop()
        new_col = len(header_row)
    new_col = len(header_row)
    cell = f"{_col_letter(new_col)}{row_1based}"
    ws.update(values=[[name]], range_name=cell)
    headers[key] = new_col
    if header_idx < len(values):
        while len(values[header_idx]) <= new_col:
            values[header_idx].append("")
        values[header_idx][new_col] = name
    logger.info("Sheets: added header %r at %s", name, cell)
    return values, headers


# Sheet owns these via formulas — bot must never overwrite them.
_FORMULA_OWNED = frozenset(
    {
        "#",
        "overall band",
        "overall band score",
        "performance",
        "released?",
        "released",
        "total sessions",
    }
)


_NUMERIC_HEADERS = frozenset(
    {
        "listening",
        "reading",
        "writing",
        "speaking",
        "pc (1-10)",
        "score (0-9)",
    }
)


def _cell_value(header_key: str, value: str | int | float) -> str | int | float:
    """Scores must be numbers — text '6.0' breaks AVERAGEIF → empty Overall."""
    if header_key in _NUMERIC_HEADERS or isinstance(value, (int, float)):
        raw = str(value).strip().replace(",", ".")
        try:
            num = float(raw)
            return int(num) if num.is_integer() else num
        except ValueError:
            return str(value)
    return str(value)


def _write_fields(
    ws,
    row_1based: int,
    headers: dict[str, int],
    fields: dict[str, str | int],
) -> None:
    """
    Write only non-empty mapped cells.

    Never blanks a cell and never touches formula-owned columns (#, Overall,
    Performance, Released?, …). Full-row updates were wiping sheet formulas.
    USER_ENTERED so Sheets parses 6.5 as a number (formulas keep working).
    """
    data: list[dict] = []
    for name, value in fields.items():
        if value is None or str(value).strip() == "":
            continue
        key = _norm(name)
        if key in _FORMULA_OWNED:
            continue
        col = headers.get(key)
        if col is None:
            continue
        data.append(
            {
                "range": f"{_col_letter(col)}{row_1based}",
                "values": [[_cell_value(key, value)]],
            }
        )
    if data:
        ws.batch_update(data, value_input_option="USER_ENTERED")


# Columns that may be pre-filled by sheet formulas for hundreds of empty rows
# (e.g. Released? = "⏳ Pending"). Must NOT count as real data when appending.
_FILLER_ONLY_HEADERS = frozenset(
    {
        "released?",
        "released",
        "notes",
        "module",
        "attendance",
        "bot notified?",
    }
)


def _next_append_row(
    values: list[list[str]],
    header_idx: int,
    headers: dict[str, int],
    *,
    key_headers: tuple[str, ...] = (
        "student id",
        "full name",
        "student name",
        "date",
        "test date",
    ),
) -> int:
    """
    1-based sheet row for the next record.

    Picks the first row after the header that has no real key data.
    Sheet formulas often prefill Released?=Pending for hundreds of empty
    rows; those must not push appends to row 500+. Orphan rows below a
    gap are ignored so new writes stay contiguous from the top.
    """
    key_cols = [headers[k] for k in key_headers if k in headers]
    filler_cols = {headers[k] for k in _FILLER_ONLY_HEADERS if k in headers}

    def _has_key(row: list) -> bool:
        if key_cols:
            return any(c < len(row) and str(row[c]).strip() for c in key_cols)
        for j, cell in enumerate(row):
            if j in filler_cols:
                continue
            if str(cell).strip():
                return True
        return False

    for i, row in enumerate(values[header_idx + 1 :], start=header_idx + 2):
        if not _has_key(row):
            return i
    return len(values) + 1


def _telegram(user) -> str:
    return f"@{user.username}" if user.username else ""


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _norm_date(value: str) -> str:
    """Normalize sheet/bot dates to dd/mm/YYYY for comparison."""
    raw = (value or "").strip().replace(".", "/").replace("-", "/")
    if not raw:
        return ""
    for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw.lower()


def _cell(row: list[str], col: int | None) -> str:
    if col is None or col >= len(row):
        return ""
    return str(row[col]).strip()


def split_name(full_name: str) -> tuple[str, str]:
    """'Ivan Petrov' → ('Ivan', 'Petrov'); single token → (token, '')."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def parse_result_scores(text: str) -> dict[str, str]:
    """
    Extract Listening/Reading/Writing/Speaking/Overall from free-form admin text.
    Supports labels and compact forms: L 7.0 / Listening: 7 / Overall Band 6.5
    """
    raw = text or ""
    out: dict[str, str] = {}
    patterns = {
        "Listening": r"(?:listening|\bL\b)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
        "Reading": r"(?:reading|\bR\b)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
        "Writing": r"(?:writing|\bW\b)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
        "Speaking": r"(?:speaking|\bS\b)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
        "Overall Band": (
            r"(?:overall\s*band(?:\s*score)?|overall|\bOA\b|\bOV\b)"
            r"\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)"
        ),
    }
    for key, pat in patterns.items():
        m = re.search(pat, raw, re.I)
        if m:
            out[key] = m.group(1).replace(",", ".")
    return out


def _person_match_row(
    values: list[list[str]],
    header_idx: int,
    headers: dict[str, int],
    *,
    full_name: str,
    phone: str,
    telegram: str,
    dob: str,
) -> tuple[int | None, str | None]:
    """
    Find Students row where person data fully matches
    (Full Name + Phone + Telegram + Date of Birth).
    Returns (1-based row, student_id) or (None, None).
    """
    name_col = headers.get("full name")
    phone_col = headers.get("phone")
    tg_col = headers.get("telegram")
    dob_col = headers.get("date of birth")
    id_col = headers.get("student id")
    want_name = (full_name or "").strip().lower()
    want_phone = re.sub(r"\D", "", phone or "")
    want_tg = (telegram or "").strip().lower().lstrip("@")
    want_dob = _norm_date(dob)
    if not want_name:
        return None, None

    for i, row in enumerate(values[header_idx + 1 :], start=header_idx + 2):
        if _cell(row, name_col).lower() != want_name:
            continue
        row_phone = re.sub(r"\D", "", _cell(row, phone_col))
        if row_phone != want_phone:
            continue
        row_tg = _cell(row, tg_col).lower().lstrip("@")
        if row_tg != want_tg:
            continue
        # If DOB column absent in sheet, ignore DOB; if present — must match exactly
        if dob_col is not None:
            if _norm_date(_cell(row, dob_col)) != want_dob:
                continue
        sid = _cell(row, id_col) if id_col is not None else ""
        return i, sid or None
    return None, None


def _resolve_student_id(
    values: list[list[str]],
    header_idx: int,
    headers: dict[str, int],
    booking: Booking,
) -> str | None:
    _, existing_id = _person_match_row(
        values,
        header_idx,
        headers,
        full_name=booking.full_name_en,
        phone=booking.user.phone or "",
        telegram=_telegram(booking.user),
        dob=_fmt_date(booking.birth_date),
    )
    return existing_id


def _resolve_student_for_booking(
    students_ws,
    s_values: list[list[str]],
    s_hidx: int,
    s_headers: dict[str, int],
    booking: Booking,
) -> tuple[str, list[list[str]], dict[str, int], bool]:
    """
    Fully matching person data → reuse Student ID (no new Students row).
    Different data (even same TG) → new Student ID + new Students row.
    """
    existing_id = _resolve_student_id(s_values, s_hidx, s_headers, booking)
    if existing_id:
        return existing_id, s_values, s_headers, False

    user = booking.user
    id_col = s_headers.get("student id")
    sheet_uid = _next_student_id(s_values, s_hidx, id_col)
    enroll = _fmt_date(booking.exam_date.exam_day)
    fields: dict[str, str | int] = {
        "Student ID": sheet_uid,
        "Full Name": booking.full_name_en,
        "Phone": user.phone or "",
        "Telegram": _telegram(user),
        "Enrollment Date": enroll,
        "Date of Birth": _fmt_date(booking.birth_date),
    }
    row_i = _next_append_row(s_values, s_hidx, s_headers)
    _write_fields(students_ws, row_i, s_headers, fields)
    # Keep in-memory cache roughly in sync for same-request lookups
    width = max(len(r) for r in s_values) if s_values else len(s_headers)
    stub = [""] * width
    for name, value in fields.items():
        col = s_headers.get(_norm(name))
        if col is not None:
            while len(stub) <= col:
                stub.append("")
            stub[col] = str(value)
    s_values = s_values + [stub]
    return sheet_uid, s_values, s_headers, True


def _results_person_fields(booking: Booking, sheet_uid: str) -> dict[str, str | int]:
    first, last = split_name(booking.full_name_en)
    return {
        "Student ID": sheet_uid,
        "User ID": sheet_uid,
        "Student Name": booking.full_name_en,
        "Name": first,
        "Surname": last,
        "First Name": first,
        "Last Name": last,
    }


def _find_data_row(
    values: list[list[str]],
    header_idx: int,
    headers: dict[str, int],
    *,
    student_id: str,
    date_header: str,
    date_value: str,
    extra: dict[str, str] | None = None,
) -> int | None:
    """Return 1-based sheet row matching Student ID + date (+ optional extras)."""
    id_col = headers.get("student id")
    date_col = headers.get(_norm(date_header))
    if id_col is None or not student_id:
        return None
    want_date = _norm_date(date_value)
    extra = extra or {}
    for i, row in enumerate(values[header_idx + 1 :], start=header_idx + 2):
        if id_col >= len(row) or str(row[id_col]).strip().lower() != student_id.lower():
            continue
        if date_col is not None:
            if date_col >= len(row) or _norm_date(str(row[date_col])) != want_date:
                continue
        ok = True
        for hname, hval in extra.items():
            c = headers.get(_norm(hname))
            if c is None:
                continue
            cell = _cell(row, c)
            # Normalize dates in extras when header looks like a date field
            if "date" in _norm(hname):
                if _norm_date(cell) != _norm_date(hval):
                    ok = False
                    break
            elif cell != hval:
                ok = False
                break
        if ok:
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
        s_values = students.get_all_values()
        s_hidx, s_headers = find_header_row(s_values)
        s_values, s_headers = _ensure_header(
            students, s_values, s_hidx, s_headers, "Date of Birth"
        )

        sheet_uid, s_values, s_headers, created = _resolve_student_for_booking(
            students, s_values, s_hidx, s_headers, booking
        )
        user.sheet_user_id = sheet_uid
        await session.flush()
        if created:
            logger.info("Students: new row %s for booking #%s", sheet_uid, booking.id)
        else:
            logger.info(
                "Students: reuse %s for booking #%s (same person data)",
                sheet_uid,
                booking.id,
            )

        # Session Log
        sess_values = sessions.get_all_values()
        sess_hidx, sess_headers = find_header_row(sess_values)
        exam = _fmt_date(booking.exam_date.exam_day)
        examiner_code = ""
        if booking.speaking_examiner:
            examiner_code = (
                booking.speaking_examiner.teacher_code
                or booking.speaking_examiner.contact
                or ""
            )
        sess_fields: dict[str, str | int] = {
            "Date": exam,
            "Session": booking.slot,
            "Student ID": sheet_uid,
            "Student Name": booking.full_name_en,
            "Speaking Teacher ID": examiner_code,
            "Payment": "✅ Paid",
            "Bot Notified?": "✅ Sent",
        }
        _write_fields(
            sessions,
            _next_append_row(sess_values, sess_hidx, sess_headers),
            sess_headers,
            sess_fields,
        )

        # Results stub (scores filled later on_result_saved)
        r_values = results.get_all_values()
        r_hidx, r_headers = find_header_row(r_values)
        for hdr in ("Name", "Surname"):
            r_values, r_headers = _ensure_header(
                results, r_values, r_hidx, r_headers, hdr
            )
        existing = _find_data_row(
            r_values,
            r_hidx,
            r_headers,
            student_id=sheet_uid,
            date_header="Test Date",
            date_value=exam,
        )
        if existing is None:
            # Only identity + date. # / Overall / Performance / Released? /
            # Student Name stay as sheet formulas (Name pulls from Students).
            person = _results_person_fields(booking, sheet_uid)
            fields: dict[str, str | int] = {
                "Test Date": exam,
                "Student ID": sheet_uid,
                "Name": person["Name"],
                "Surname": person["Surname"],
            }
            _write_fields(
                results,
                _next_append_row(r_values, r_hidx, r_headers),
                r_headers,
                fields,
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
        students = sh.worksheet(STUDENTS_SHEET)
        s_values = students.get_all_values()
        s_hidx, s_headers = find_header_row(s_values)
        s_values, s_headers = _ensure_header(
            students, s_values, s_hidx, s_headers, "Date of Birth"
        )
        matched_id = _resolve_student_id(s_values, s_hidx, s_headers, booking)
        uid = matched_id or booking.user.sheet_user_id or ""
        if matched_id and booking.user.sheet_user_id != matched_id:
            booking.user.sheet_user_id = matched_id
            await session.flush()

        results = sh.worksheet(RESULTS_SHEET)
        exam = _fmt_date(booking.exam_date.exam_day)
        all_rows = results.get_all_values()
        hidx, headers = find_header_row(all_rows)
        for hdr in ("Name", "Surname"):
            all_rows, headers = _ensure_header(results, all_rows, hidx, headers, hdr)

        text = booking.result_text or ""
        scores = parse_result_scores(text)
        person = _results_person_fields(booking, uid)
        # Scores only — Overall / Performance / # / Released? = sheet formulas.
        # Writing/Speaking cells: bot is source when admin sends result in TG.
        fields: dict[str, str | int] = {
            "Student ID": uid,
            "Test Date": exam,
            "Name": person["Name"],
            "Surname": person["Surname"],
            "Listening": scores.get("Listening", ""),
            "Reading": scores.get("Reading", ""),
            "Writing": scores.get("Writing", ""),
            "Speaking": scores.get("Speaking", ""),
        }

        row_i = _find_data_row(
            all_rows,
            hidx,
            headers,
            student_id=uid,
            date_header="Test Date",
            date_value=exam,
        )
        if row_i is None:
            row_i = _next_append_row(all_rows, hidx, headers)
            logger.info(
                "Sheets Results appended uid=%s scores=%s",
                uid,
                {k: scores[k] for k in scores},
            )
        else:
            logger.info(
                "Sheets Results updated row %s uid=%s scores=%s",
                row_i,
                uid,
                {k: scores[k] for k in scores},
            )
        _write_fields(results, row_i, headers, fields)
    except Exception:
        logger.exception("Sheets on_result_saved failed")


async def on_post_exam(
    session: AsyncSession, booking: Booking, settings: Settings
) -> None:
    """Fill Speaking Teacher ID in Session Log when examiner chosen."""
    if not _enabled(settings):
        return
    try:
        from app.db.models import SpeakingExaminer

        sh = _open(settings)
        uid = (booking.user.sheet_user_id or "").strip()
        if not uid:
            students = sh.worksheet(STUDENTS_SHEET)
            s_values = students.get_all_values()
            s_hidx, s_headers = find_header_row(s_values)
            matched_id = _resolve_student_id(s_values, s_hidx, s_headers, booking)
            uid = matched_id or ""

        # Prefer @contact (what admins see in TG), fallback to teacher code
        code = ""
        examiner = booking.speaking_examiner
        if examiner is None and booking.speaking_examiner_id:
            examiner = await session.get(SpeakingExaminer, booking.speaking_examiner_id)
        if examiner:
            code = (examiner.contact or "").strip() or (examiner.teacher_code or "").strip()
        if not code:
            logger.warning(
                "Sheets on_post_exam: no examiner contact for booking #%s", booking.id
            )
            return

        sessions = sh.worksheet(SESSION_SHEET)
        exam = _fmt_date(booking.exam_date.exam_day)
        rows = sessions.get_all_values()
        hidx, headers = find_header_row(rows)
        teacher_col = headers.get("speaking teacher id")
        if teacher_col is None:
            logger.warning("Session Log has no Speaking Teacher ID column")
            return

        row_i = None
        if uid:
            row_i = _find_data_row(
                rows,
                hidx,
                headers,
                student_id=uid,
                date_header="Date",
                date_value=exam,
                extra={"Session": booking.slot},
            )
            if row_i is None:
                # Fallback: same student+date without session match
                row_i = _find_data_row(
                    rows,
                    hidx,
                    headers,
                    student_id=uid,
                    date_header="Date",
                    date_value=exam,
                )
        if row_i is None:
            # Fallback: Student Name + Date + Session
            name_col = headers.get("student name")
            date_col = headers.get("date")
            sess_col = headers.get("session")
            want_name = (booking.full_name_en or "").strip().lower()
            want_date = _norm_date(exam)
            want_slot = (booking.slot or "").strip()
            for i, row in enumerate(rows[hidx + 1 :], start=hidx + 2):
                if name_col is not None and _cell(row, name_col).lower() != want_name:
                    continue
                if date_col is not None and _norm_date(_cell(row, date_col)) != want_date:
                    continue
                if sess_col is not None and want_slot and _cell(row, sess_col) != want_slot:
                    continue
                row_i = i
                break

        if row_i is None:
            logger.warning(
                "Sheets on_post_exam: Session row not found booking #%s uid=%s date=%s slot=%s",
                booking.id,
                uid,
                exam,
                booking.slot,
            )
            return

        sessions.update(
            values=[[code]],
            range_name=f"{_col_letter(teacher_col)}{row_i}",
        )
        logger.info(
            "Sheets Session Log speaking teacher row=%s booking=#%s → %s",
            row_i,
            booking.id,
            code,
        )
    except Exception:
        logger.exception("Sheets on_post_exam failed")
