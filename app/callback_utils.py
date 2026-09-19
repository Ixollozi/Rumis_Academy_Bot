from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


async def safe_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    """Answer callback; ignore if already answered by middleware."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
        # Already answered (early middleware) or query expired
        if text and show_alert:
            # Fallback: send a short chat message for important alerts
            try:
                await callback.message.answer(f"⚠️ {text}")
            except Exception:
                pass
