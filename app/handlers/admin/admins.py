from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.db.models import BotAdmin
from app.keyboards import (
    admin_admins_kb,
    admin_menu_kb,
    cancel_kb,
    main_menu_kb,
)
from app.locales.i18n import all_t, t
from app.services import admin_access
from app.states import AdminSG

router = Router(name="admin_admins")


def _label(admin: BotAdmin) -> str:
    uname = f" @{admin.username}" if admin.username else ""
    mark = " 🔒" if admin.is_owner else ""
    return f"{admin.tg_id}{uname}{mark}"


async def _render_list(
    callback: CallbackQuery, session: AsyncSession, lang: str
) -> None:
    admins = await repo.list_bot_admins(session)
    lines = [t(lang, "admin_admins_title"), ""]
    if not admins:
        lines.append(t(lang, "admin_admins_empty"))
    else:
        for a in admins:
            lines.append(f"• {_label(a)}")
        lines.append("")
        lines.append(t(lang, "admin_admins_hint"))
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_admins_kb(lang, admins),
    )


@router.callback_query(F.data == "adm:admins")
async def admins_menu(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    await state.clear()
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await _render_list(callback, session, user.lang)
    await callback.answer()


@router.callback_query(F.data == "adm:admin:add")
async def admin_add_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.set_state(AdminSG.add_admin)
    await callback.message.answer(
        t(user.lang, "admin_admins_ask_id"),
        reply_markup=cancel_kb(user.lang),
    )
    await callback.answer()


@router.message(AdminSG.add_admin, F.text.in_(all_t("btn_cancel")))
async def admin_add_cancel(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    await state.clear()
    user = await repo.get_or_create_user(session, message.from_user.id)
    await message.answer(
        t(user.lang, "booking_cancelled"),
        reply_markup=main_menu_kb(user.lang, is_admin=True),
    )
    await message.answer(
        t(user.lang, "admin_menu"),
        reply_markup=admin_menu_kb(user.lang),
    )


@router.message(AdminSG.add_admin)
async def admin_add_save(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    user = await repo.get_or_create_user(session, message.from_user.id)
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer(t(user.lang, "admin_admins_bad_id"))
        return
    tg_id = int(raw)
    if tg_id <= 0:
        await message.answer(t(user.lang, "admin_admins_bad_id"))
        return

    existing = await repo.get_bot_admin(session, tg_id)
    if existing:
        await state.clear()
        await message.answer(
            t(user.lang, "admin_admins_already"),
            reply_markup=main_menu_kb(user.lang, is_admin=True),
        )
        await message.answer(
            t(user.lang, "admin_menu"),
            reply_markup=admin_menu_kb(user.lang),
        )
        return

    await repo.add_bot_admin(session, tg_id)
    await admin_access.refresh_cache(session, settings.env_owner_ids)
    await state.clear()

    await message.answer(
        t(user.lang, "admin_admins_added", tg_id=tg_id),
        reply_markup=main_menu_kb(user.lang, is_admin=True),
    )
    await message.answer(
        t(user.lang, "admin_menu"),
        reply_markup=admin_menu_kb(user.lang),
    )

    # Best-effort notify new admin if they already started the bot
    try:
        target = await repo.get_or_create_user(session, tg_id)
        await message.bot.send_message(
            tg_id,
            t(target.lang, "admin_admins_you_are_admin"),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm:admin:rm:"))
async def admin_remove(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[3])
    user = await repo.get_or_create_user(session, callback.from_user.id)

    err = await repo.remove_bot_admin(session, tg_id)
    if err == "not_found":
        await callback.answer(t(user.lang, "admin_admins_not_found"), show_alert=True)
        await _render_list(callback, session, user.lang)
        return
    if err == "is_owner":
        await callback.answer(t(user.lang, "admin_admins_owner_locked"), show_alert=True)
        return
    if err == "last_admin":
        await callback.answer(t(user.lang, "admin_admins_last"), show_alert=True)
        return

    await admin_access.refresh_cache(session, settings.env_owner_ids)
    await callback.answer(t(user.lang, "admin_admins_removed", tg_id=tg_id), show_alert=True)
    await _render_list(callback, session, user.lang)

    try:
        removed_user = await repo.get_or_create_user(session, tg_id)
        await callback.bot.send_message(
            tg_id,
            t(removed_user.lang, "admin_admins_you_removed"),
            reply_markup=main_menu_kb(removed_user.lang, is_admin=False),
        )
    except Exception:
        pass
