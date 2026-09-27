"""Track and finalize admin inline cards so all admins see the same outcome."""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Booking

logger = logging.getLogger(__name__)


def _parse(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [
                x
                for x in data
                if isinstance(x, dict) and "chat_id" in x and "message_id" in x
            ]
    except json.JSONDecodeError:
        pass
    return []


async def remember_card(
    session: AsyncSession, booking: Booking, *, chat_id: int, message_id: int
) -> Booking:
    cards = _parse(booking.admin_card_messages)
    key = (int(chat_id), int(message_id))
    if not any((int(c["chat_id"]), int(c["message_id"])) == key for c in cards):
        cards.append({"chat_id": key[0], "message_id": key[1]})
    booking.admin_card_messages = json.dumps(cards, ensure_ascii=False)
    await session.flush()
    refreshed = await repo.get_booking(session, booking.id)
    return refreshed  # type: ignore[return-value]


async def clear_cards(session: AsyncSession, booking: Booking) -> Booking:
    booking.admin_card_messages = None
    await session.flush()
    refreshed = await repo.get_booking(session, booking.id)
    return refreshed  # type: ignore[return-value]


async def finalize_cards(
    bot: Bot,
    session: AsyncSession,
    booking: Booking,
    footer: str,
    *,
    also: tuple[int, int] | None = None,
    base_text: str | None = None,
) -> None:
    """Remove keyboards and append footer on all remembered admin cards."""
    cards = _parse(booking.admin_card_messages)
    if also:
        chat_id, message_id = also
        if not any(
            int(c["chat_id"]) == chat_id and int(c["message_id"]) == message_id
            for c in cards
        ):
            cards.append({"chat_id": chat_id, "message_id": message_id})

    new_text = None
    if base_text:
        new_text = base_text if footer in base_text else f"{base_text}\n\n{footer}"

    seen: set[tuple[int, int]] = set()
    for card in cards:
        chat_id = int(card["chat_id"])
        message_id = int(card["message_id"])
        if (chat_id, message_id) in seen:
            continue
        seen.add((chat_id, message_id))
        if new_text:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    reply_markup=None,
                )
                continue
            except Exception:
                logger.debug(
                    "finalize text failed chat=%s msg=%s",
                    chat_id,
                    message_id,
                    exc_info=True,
                )
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            logger.debug(
                "finalize markup failed chat=%s msg=%s",
                chat_id,
                message_id,
                exc_info=True,
            )

    await clear_cards(session, booking)
