from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, TelegramObject, Update

from app.db import get_session_factory


class DbSessionMiddleware(BaseMiddleware):
    """One DB session per update; single commit at the end."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        factory = get_session_factory()
        async with factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class SettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self.settings
        return await handler(event, data)


class CallbackAnswerMiddleware(BaseMiddleware):
    """
    Answer callback queries immediately so Telegram stops the loading spinner.
    Handlers may still call callback.answer(...) again for alerts — those
    TelegramBadRequest are ignored via safe_answer helper.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Outer middleware may receive Update; answer on CallbackQuery events only.
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except TelegramBadRequest:
                pass
            data["callback_answered"] = True
        return await handler(event, data)


class UpdateCallbackAnswerMiddleware(BaseMiddleware):
    """Register on dp.update — answer CallbackQuery as soon as update arrives."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and event.callback_query is not None:
            try:
                await event.callback_query.answer()
            except TelegramBadRequest:
                pass
            data["callback_answered"] = True
        return await handler(event, data)
