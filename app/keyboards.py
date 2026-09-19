from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.db.models import ExamDate, SlotTime
from app.locales.i18n import t


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_share_phone"), request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_kb(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(lang, "btn_book"))],
        [KeyboardButton(text=t(lang, "btn_my_tests")), KeyboardButton(text=t(lang, "btn_results"))],
        [KeyboardButton(text=t(lang, "btn_location")), KeyboardButton(text=t(lang, "btn_contact_admin"))],
        [KeyboardButton(text=t(lang, "btn_change_lang"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(lang, "btn_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_cancel"))]],
        resize_keyboard=True,
    )


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_confirm"), callback_data="book:confirm"
                ),
                InlineKeyboardButton(
                    text=t(lang, "btn_cancel"), callback_data="book:cancel"
                ),
            ]
        ]
    )


def dates_kb(lang: str, dates: list[ExamDate]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📅 {d.exam_day.strftime('%d.%m.%Y')}",
                callback_data=f"book:date:{d.id}",
            )
        ]
        for d in dates
    ]
    rows.append(
        [InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="book:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🕐 {s.value}", callback_data=f"book:slot:{s.name}"
                )
                for s in SlotTime
            ],
            [InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="book:cancel")],
        ]
    )


def paid_kb(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_i_paid"),
                    callback_data=f"pay:done:{booking_id}",
                )
            ]
        ]
    )


def admin_menu_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "admin_dates"), callback_data="adm:dates")],
            [InlineKeyboardButton(text=t(lang, "admin_apps"), callback_data="adm:apps")],
            [InlineKeyboardButton(text=t(lang, "admin_prices"), callback_data="adm:prices")],
            [InlineKeyboardButton(text=t(lang, "admin_results"), callback_data="adm:results")],
            [InlineKeyboardButton(text=t(lang, "admin_post_exam"), callback_data="adm:post")],
            [InlineKeyboardButton(text=t(lang, "admin_export"), callback_data="adm:export")],
        ]
    )


def admin_dates_list_kb(lang: str, dates: list[ExamDate]) -> InlineKeyboardMarkup:
    rows = []
    for d in dates:
        label = f"{d.exam_day.strftime('%d.%m.%Y')} lim={d.seat_limit}"
        if d.is_closed:
            label += " [×]"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label, callback_data=f"adm:date:{d.id}"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "admin_btn_add_date"), callback_data="adm:date:add"
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "admin_btn_back"), callback_data="adm:home"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_date_actions_kb(lang: str, exam_date_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_btn_set_limit"),
                    callback_data=f"adm:limit:{exam_date_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_btn_close_date"),
                    callback_data=f"adm:close:{exam_date_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_btn_back"), callback_data="adm:dates"
                )
            ],
        ]
    )


def admin_price_assign_kb(
    lang: str, booking_id: int, own: int, new: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(own), callback_data=f"adm:price:{booking_id}:{own}"
                ),
                InlineKeyboardButton(
                    text=str(new), callback_data=f"adm:price:{booking_id}:{new}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_reject"),
                    callback_data=f"adm:reject:{booking_id}",
                )
            ],
        ]
    )


def admin_payment_kb(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_mark_paid"),
                    callback_data=f"adm:paid:{booking_id}",
                ),
                InlineKeyboardButton(
                    text=t(lang, "admin_mark_unpaid"),
                    callback_data=f"adm:unpay:{booking_id}",
                ),
            ]
        ]
    )


def admin_apps_filter_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_apps_need_price"),
                    callback_data="adm:apps:pending_price",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_apps_payment_review"),
                    callback_data="adm:apps:payment_review",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_apps_awaiting"),
                    callback_data="adm:apps:awaiting_payment",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_apps_paid"), callback_data="adm:apps:paid"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "admin_btn_back"), callback_data="adm:home"
                )
            ],
        ]
    )


def admin_result_pick_kb(lang: str, booking_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{bid}", callback_data=f"adm:res:{bid}")]
        for bid in booking_ids
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "admin_btn_back"), callback_data="adm:home"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_post_pick_kb(lang: str, booking_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Send #{bid}", callback_data=f"adm:postsend:{bid}"
            )
        ]
        for bid in booking_ids
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "admin_btn_back"), callback_data="adm:home"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
