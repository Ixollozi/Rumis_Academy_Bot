from __future__ import annotations

import re
from datetime import date, datetime
from html import escape as html_escape


FULL_NAME_RE = re.compile(
    r"^[A-Za-z][A-Za-z']*(?:[ \-][A-Za-z][A-Za-z']*)+$|^[A-Za-z][A-Za-z']{1,}$"
)


def normalize_full_name(value: str) -> str | None:
    cleaned = " ".join(value.strip().split())
    if not FULL_NAME_RE.match(cleaned):
        return None
    # Preserve letters after apostrophe (O'Brien)
    parts = []
    for word in cleaned.replace("-", " - ").split():
        if word == "-":
            parts.append("-")
            continue
        if "'" in word:
            segs = word.split("'")
            parts.append("'".join(s[:1].upper() + s[1:].lower() if s else "" for s in segs))
        else:
            parts.append(word[:1].upper() + word[1:].lower())
    # Re-join hyphens without extra spaces: "Mary - Jane" → "Mary-Jane"
    out = " ".join(parts).replace(" - ", "-")
    return out

def parse_dmY(value: str) -> date | None:
    value = value.strip().replace(".", "/").replace("-", "/")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def format_dmY(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def format_price(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ")


def h(value: object) -> str:
    """Escape for Telegram HTML parse mode."""
    return html_escape(str(value), quote=False)
