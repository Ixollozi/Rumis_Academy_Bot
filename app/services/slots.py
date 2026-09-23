"""Exam slot time helpers (timezone-aware availability)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db.models import ALL_SLOT_HOURS


def parse_hhmm(value: str) -> time:
    hour, minute = map(int, value.split(":"))
    return time(hour=hour, minute=minute)


def slot_start_dt(exam_day: date, slot: str, tz_name: str) -> datetime:
    """
    Slot '00:00' means midnight at the *end* of the exam day
    (i.e. start of the next calendar day).
    """
    tz = ZoneInfo(tz_name)
    if slot == "00:00":
        return datetime.combine(exam_day + timedelta(days=1), time(0, 0), tzinfo=tz)
    return datetime.combine(exam_day, parse_hhmm(slot), tzinfo=tz)


def slot_is_open(exam_day: date, slot: str, tz_name: str, now: datetime | None = None) -> bool:
    """Slot is bookable until its start time (exclusive): 10:00 open until 09:59."""
    now = now or datetime.now(ZoneInfo(tz_name))
    return now < slot_start_dt(exam_day, slot, tz_name)


def post_exam_due(exam_day: date, slot: str, tz_name: str) -> datetime:
    return slot_start_dt(exam_day, slot, tz_name) + timedelta(hours=2, minutes=50)


def sort_slot_values(values: list[str]) -> list[str]:
    order = {v: i for i, v in enumerate(ALL_SLOT_HOURS)}
    return sorted(values, key=lambda v: order.get(v, 99))
