from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_menu_kb
from app.locales.i18n import t
from app.services.excel_export import send_excel

router = Router(name="admin_export")


@router.callback_query(F.data == "adm:export")
async def export_excel(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.answer()
    await send_excel(callback.bot, callback.from_user.id, session)
    await callback.message.answer(
        t(user.lang, "admin_export_ready"), reply_markup=admin_menu_kb(user.lang)
    )
