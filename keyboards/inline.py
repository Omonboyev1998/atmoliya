from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_members_keyboard(members: List[Dict[str, Any]], action_prefix: str = "member", page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    total_pages = (len(members) + page_size - 1) // page_size
    start_idx = page * page_size
    current_members = members[start_idx : start_idx + page_size]

    buttons = []
    for m in current_members:
        btn_text = f"👤 {m['full_name']} ({m['birth_date'][:5]})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"{action_prefix}:{m['id']}")])

    # Sahifalash tugmalari
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{action_prefix}_page:{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"{action_prefix}_page:{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Yopish", callback_data="close_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_member_due_selection_keyboard(member_id: int, monthly_debts: list, birthday_debts: list) -> InlineKeyboardMarkup:
    buttons = []

    # Oylik qarzlar
    for d in monthly_debts:
        text = f"📅 {d['period_name']} (50 000 so'm)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"pay_monthly:{d['id']}:{member_id}")])

    # Tug'ilgan kun qarzlari
    for bd in birthday_debts:
        text = f"🎂 {bd['celebrant_name']} (25 000 so'm)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"pay_bday:{bd['id']}:{member_id}")])

    if not monthly_debts and not birthday_debts:
        buttons.append([InlineKeyboardButton(text="✅ Bu xodimning qarzi yo'q", callback_data="none")])

    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_members")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_birthday_gift_keyboard(event_id: int, gift_given: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not gift_given:
        buttons.append([InlineKeyboardButton(text="🎁 500 000 so'm mukofot topshirildi", callback_data=f"give_gift:{event_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Yopish", callback_data="close_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard(action: str, id_val: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, tasdiqlayman", callback_data=f"confirm_{action}:{id_val}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="close_menu")
            ]
        ]
    )

def get_debt_remind_keyboard(member_id: int, has_tg: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_tg:
        buttons.append([InlineKeyboardButton(text="📩 Eslatma xabari yuborish", callback_data=f"remind_debt:{member_id}")])
    buttons.append([InlineKeyboardButton(text="💵 To'lovni yozish", callback_data=f"pay_for_member:{member_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Karta rekvizitlarini o'zgartirish", callback_data="set_card")],
            [InlineKeyboardButton(text="👥 Yangi admin tayinlash", callback_data="add_admin")],
            [InlineKeyboardButton(text="🔙 Yopish", callback_data="close_menu")]
        ]
    )
