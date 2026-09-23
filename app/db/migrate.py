"""Lightweight schema upgrades for SQLite/Postgres without full Alembic dance."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)


async def _column_names(conn: AsyncConnection, table: str) -> set[str]:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {r[1] for r in rows.fetchall()}
    rows = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    )
    return {r[0] for r in rows.fetchall()}


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = await conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
            ),
            {"t": table},
        )
        return rows.first() is not None
    rows = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ),
        {"t": table},
    )
    return rows.first() is not None


async def upgrade_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        if not await _table_exists(conn, "bookings"):
            return
        cols = await _column_names(conn, "bookings")
        dialect = conn.engine.dialect.name

        # payment receipt
        if "payment_file_id" not in cols:
            await conn.execute(
                text("ALTER TABLE bookings ADD COLUMN payment_file_id VARCHAR(256)")
            )
            logger.info("Added bookings.payment_file_id")
        if "payment_file_type" not in cols:
            await conn.execute(
                text("ALTER TABLE bookings ADD COLUMN payment_file_type VARCHAR(16)")
            )
            logger.info("Added bookings.payment_file_type")
        if "speaking_examiner_id" not in cols:
            await conn.execute(
                text("ALTER TABLE bookings ADD COLUMN speaking_examiner_id INTEGER")
            )
            logger.info("Added bookings.speaking_examiner_id")
        if "speaking_prompted" not in cols:
            await conn.execute(
                text(
                    "ALTER TABLE bookings ADD COLUMN speaking_prompted BOOLEAN DEFAULT 0"
                )
            )
            logger.info("Added bookings.speaking_prompted")

        # users.sheet_user_id
        if await _table_exists(conn, "users"):
            ucols = await _column_names(conn, "users")
            if "sheet_user_id" not in ucols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN sheet_user_id VARCHAR(32)")
                )
                logger.info("Added users.sheet_user_id")

        # Normalize slot column: old enum names s10/s13/s16 → HH:MM
        if dialect == "sqlite":
            await conn.execute(
                text("UPDATE bookings SET slot='10:00' WHERE slot IN ('s10','10:00') OR slot='SlotTime.s10'")
            )
            await conn.execute(
                text("UPDATE bookings SET slot='13:00' WHERE slot IN ('s13') OR slot='SlotTime.s13'")
            )
            await conn.execute(
                text("UPDATE bookings SET slot='16:00' WHERE slot IN ('s16') OR slot='SlotTime.s16'")
            )
            # If still enum-like string values without colon
            await conn.execute(
                text(
                    "UPDATE bookings SET slot='10:00' WHERE slot NOT LIKE '%:%' AND (slot LIKE '%10%' OR slot='') "
                )
            )
        else:
            await conn.execute(
                text(
                    "UPDATE bookings SET slot='10:00' WHERE slot IN ('s10','SlotTime.s10')"
                )
            )
            await conn.execute(
                text(
                    "UPDATE bookings SET slot='13:00' WHERE slot IN ('s13','SlotTime.s13')"
                )
            )
            await conn.execute(
                text(
                    "UPDATE bookings SET slot='16:00' WHERE slot IN ('s16','SlotTime.s16')"
                )
            )
