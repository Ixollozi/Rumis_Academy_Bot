from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_menu_kb, admin_notify_audience_kb, cancel_kb, main_menu_kb
from app.locales.i18n import all_t, t
from app.states import AdminSG

logger = logging.getLogger(__name__)
router = Router(name="admin_notifications")


@router.callback_query(F.data == "adm:notify")
async def notify_menu(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    await state.clear()
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_notify_pick"),
        reply_markup=admin_notify_audience_kb(user.lang),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"adm:notify:all", "adm:notify:paid"}))
async def notify_audience(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    audience = "paid" if callback.data.endswith(":paid") else "all"
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.set_state(AdminSG.broadcast)
    await state.update_data(audience=audience)
    await callback.message.answer(
        t(user.lang, "admin_notify_ask"),
        reply_markup=cancel_kb(user.lang),
    )
    await callback.answer()


@router.message(AdminSG.broadcast, F.text.in_(all_t("btn_cancel")))
async def notify_cancel(
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


@router.message(AdminSG.broadcast)
async def notify_send(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    user = await repo.get_or_create_user(session, message.from_user.id)
    if not text:
        await message.answer(t(user.lang, "admin_notify_ask"))
        return

    data = await state.get_data()
    audience = data.get("audience", "all")
    if audience == "paid":
        recipients = await repo.list_users_with_paid(session)
    else:
        recipients = await repo.list_registered_users(session)

    await state.clear()
    # Restore main reply keyboard before long send
    await message.answer(
        t(user.lang, "admin_notify_sending", total=len(recipients) or 0),
        reply_markup=main_menu_kb(user.lang, is_admin=True),
    )
    if not recipients:
        await message.answer(
            t(user.lang, "admin_notify_empty"),
            reply_markup=admin_menu_kb(user.lang),
        )
        return

    ok = 0
    fail = 0
    for recipient in recipients:
        try:
            await message.bot.send_message(recipient.tg_id, text)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                await message.bot.send_message(recipient.tg_id, text)
                ok += 1
            except Exception:
                fail += 1
                logger.exception("Notify failed for %s", recipient.tg_id)
        except TelegramForbiddenError:
            fail += 1
        except Exception:
            fail += 1
            logger.exception("Notify failed for %s", recipient.tg_id)
        await asyncio.sleep(0.05)

    await message.answer(
        t(user.lang, "admin_notify_done", ok=ok, fail=fail, total=len(recipients)),
        reply_markup=admin_menu_kb(user.lang),
    )
