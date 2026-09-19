from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repo
from app.keyboards import admin_date_actions_kb, admin_dates_list_kb, admin_menu_kb
from app.locales.i18n import t
from app.states import AdminSG
from app.utils import format_dmY, parse_dmY

router = Router(name="admin_dates")


def _admin_ok(settings: Settings, user_id: int) -> bool:
    return settings.is_admin(user_id)


@router.callback_query(F.data == "adm:home")
async def admin_home(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_menu"), reply_markup=admin_menu_kb(user.lang)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:dates")
async def admin_dates(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    dates = await repo.list_all_exam_dates(session)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_dates"), reply_markup=admin_dates_list_kb(user.lang, dates)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:date:add")
async def admin_add_date_start(
    callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession
) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.set_state(AdminSG.add_date)
    await callback.message.answer(t(user.lang, "admin_ask_date"))
    await callback.answer()


@router.message(AdminSG.add_date)
async def admin_add_date(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, message.from_user.id):
        return
    user = await repo.get_or_create_user(session, message.from_user.id)
    day = parse_dmY(message.text or "")
    if not day:
        await message.answer(t(user.lang, "invalid_birth_date"))
        return
    row = await repo.create_exam_date(session, day, settings.default_date_limit)
    await state.clear()
    await message.answer(
        t(
            user.lang,
            "admin_date_added",
            exam_date=format_dmY(row.exam_day),
            limit=row.seat_limit,
        ),
        reply_markup=admin_menu_kb(user.lang),
    )


@router.callback_query(F.data.startswith("adm:date:") & ~F.data.endswith(":add"))
async def admin_date_detail(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    exam_date_id = int(callback.data.split(":")[2])
    exam = await repo.get_exam_date(session, exam_date_id)
    if not exam:
        await callback.answer("not found", show_alert=True)
        return
    paid = await repo.paid_count_for_date(session, exam.id)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    text = (
        f"{exam.exam_day.strftime('%d.%m.%Y')}\n"
        f"Limit: {exam.seat_limit}\n"
        f"Paid: {paid}\n"
        f"Closed: {exam.is_closed}"
    )
    await callback.message.edit_text(
        text, reply_markup=admin_date_actions_kb(user.lang, exam.id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:limit:"))
async def admin_limit_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    exam_date_id = int(callback.data.split(":")[2])
    exam = await repo.get_exam_date(session, exam_date_id)
    if not exam:
        await callback.answer("not found", show_alert=True)
        return
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await state.set_state(AdminSG.set_limit)
    await state.update_data(exam_date_id=exam_date_id)
    await callback.message.answer(
        t(
            user.lang,
            "admin_set_limit",
            exam_date=exam.exam_day.strftime("%d.%m.%Y"),
            limit=exam.seat_limit,
        )
    )
    await callback.answer()


@router.message(AdminSG.set_limit)
async def admin_set_limit(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, message.from_user.id):
        return
    user = await repo.get_or_create_user(session, message.from_user.id)
    try:
        limit = int((message.text or "").strip())
        if limit < 1:
            raise ValueError
    except ValueError:
        await message.answer("Enter a positive integer")
        return
    data = await state.get_data()
    exam = await repo.set_exam_date_limit(session, int(data["exam_date_id"]), limit)
    await state.clear()
    await message.answer(
        t(
            user.lang,
            "admin_limit_set",
            exam_date=exam.exam_day.strftime("%d.%m.%Y"),
            limit=exam.seat_limit,
        ),
        reply_markup=admin_menu_kb(user.lang),
    )


@router.callback_query(F.data.startswith("adm:close:"))
async def admin_close_date(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if not _admin_ok(settings, callback.from_user.id):
        await callback.answer("no", show_alert=True)
        return
    exam_date_id = int(callback.data.split(":")[2])
    exam = await repo.close_exam_date(session, exam_date_id)
    user = await repo.get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t(user.lang, "admin_close_date", exam_date=exam.exam_day.strftime("%d.%m.%Y")),
        reply_markup=admin_menu_kb(user.lang),
    )
    await callback.answer()
