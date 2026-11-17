from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_member_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💳 Mening to'lovlarim va qarzim"),
                KeyboardButton(text="💰 Fond balansi")
            ],
            [
                KeyboardButton(text="🎂 Tug'ilgan kunlar taqvimi"),
                KeyboardButton(text="ℹ️ To'lov rekvizitlari")
            ]
        ],
        resize_keyboard=True
    )

def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👥 Xodimlar"),
                KeyboardButton(text="➕ Yangi xodim qo'shish")
            ],
            [
                KeyboardButton(text="💵 To'lov qabul qilish"),
                KeyboardButton(text="💸 Chiqim kiritish")
            ],
            [
                KeyboardButton(text="⚠️ Qarzdorlar ro'yxati"),
                KeyboardButton(text="📊 Excel hisobot")
            ],
            [
                KeyboardButton(text="💰 Fond balansi"),
                KeyboardButton(text="🎂 Tug'ilgan kunlar")
            ],
            [
                KeyboardButton(text="📅 Yangi oy badalini ochish"),
                KeyboardButton(text="⚙️ Sozlamalar")
            ]
        ],
        resize_keyboard=True
    )

def get_cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def get_contact_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Kontaktni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
