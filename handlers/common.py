from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DEFAULT_CARD_NUMBER, DEFAULT_CARD_HOLDER, ADMIN_IDS
from database.db import (
    is_admin,
    add_member,
    get_member_by_tg_id,
    get_all_members,
    set_member_telegram_id,
    get_member_debts,
    get_fund_stats,
    get_upcoming_birthdays,
    get_setting,
    get_all_admins
)
from keyboards.default import get_member_menu, get_admin_menu, get_cancel_menu, get_contact_menu

router = Router()

class SelfRegisterStates(StatesGroup):
    full_name = State()
    birth_date = State()
    phone = State()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    admin_status = await is_admin(tg_id)

    member = await get_member_by_tg_id(tg_id)

    if admin_status:
        text = (
            f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
            f"👑 <b>Kafedra fondi boshqaruv paneliga xush kelibsiz!</b>\n"
            f"Siz tizimda <b>Admin / G'aznachi</b> maqomidamisiz.\n\n"
            f"Quyidagi menyu orqali fond kirim-chiqimlarini, xodimlarni va badallarni boshqarishingiz mumkin."
        )
        await message.answer(text, reply_markup=get_admin_menu(), parse_mode="HTML")
        return

    if member:
        text = (
            f"Assalomu alaykum, <b>{member['full_name']}</b>!\n\n"
            f"🏛 <b>Kafedra fondi botiga xush kelibsiz!</b>\n"
            f"Bu yerda siz o'z to'lovlaringiz, kafedra fondi balansi va hamkasblaringizning tavallud ayyomlarini kuzatib borishingiz mumkin.\n\n"
            f"<i>Quyidagi tugmalardan birini tanlang:</i>"
        )
        await message.answer(text, reply_markup=get_member_menu(), parse_mode="HTML")
        return

    # Foydalanuvchi hali a'zo emas
    all_members = await get_all_members(active_only=True)
    unlinked_members = [m for m in all_members if not m["telegram_id"]]

    buttons = [
        [InlineKeyboardButton(text="📝 Kafedra a'zosi sifatida ro'yxatdan o'tish", callback_data="start_self_register")]
    ]

    if unlinked_members:
        buttons.append([InlineKeyboardButton(text="🔗 Mening ismim oldin kiritilgan (Bog'lash)", callback_data="show_unlinked_list")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
        f"🏛 <b>Kafedra fondi botiga xush kelibsiz!</b>\n\n"
        f"Siz hali kafedra a'zolari ro'yxatida emassiz.\n"
        f"Kafedra a'zosi sifatida qo'shilish uchun quyidagi <b>'Ro'yxatdan o'tish'</b> tugmasini bosing:"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- O'zini ro'yxatdan o'tkazish (Self-Registration) ---
@router.callback_query(F.data == "start_self_register")
async def start_self_register_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SelfRegisterStates.full_name)
    await callback.message.delete()
    await callback.message.answer(
        "Iltimos, to'liq <b>Familiyangiz, Ismingiz va Sharifingizni</b> kiriting:\n<i>(Masalan: Karimov Alisher Baxtiyorovich)</i>",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML"
    )

@router.message(SelfRegisterStates.full_name)
async def self_reg_name_step(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Ro'yxatdan o'tish bekor qilindi. Qayta boshlash uchun /start ni bosing.")
        return

    name = message.text.strip()
    if len(name) < 4 or len(name.split()) < 2:
        await message.answer("Iltimos, to'liq ism va familiyangizni kiriting (Masalan: Karimov Alisher Baxtiyorovich):")
        return

    await state.update_data(full_name=name)
    await state.set_state(SelfRegisterStates.birth_date)
    await message.answer(
        f"Rahmat, <b>{name}</b>!\n\n"
        f"Endi <b>tug'ilgan sanangizni</b> kiriting:\n"
        f"<i>Format: KK.OO.YYYY (Masalan: 15.05.1988)</i>",
        parse_mode="HTML"
    )

@router.message(SelfRegisterStates.birth_date)
async def self_reg_bday_step(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Ro'yxatdan o'tish bekor qilindi. Qayta boshlash uchun /start ni bosing.")
        return

    bday_text = message.text.strip()
    parts = bday_text.split(".")
    if len(parts) < 2:
        await message.answer("Noto'g'ri format! Iltimos, <b>KK.OO.YYYY</b> formatida kiriting (Masalan: 25.10.1988):", parse_mode="HTML")
        return

    try:
        day = int(parts[0])
        month = int(parts[1])
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError()
        year = parts[2] if len(parts) >= 3 else "1990"
        normalized_bday = f"{day:02d}.{month:02d}.{year}"
    except Exception:
        await message.answer("Kun yoki oy raqami xato kiritildi. Qaytadan kiriting (Masalan: 12.04.1988):")
        return

    await state.update_data(birth_date=normalized_bday)
    await state.set_state(SelfRegisterStates.phone)
    await message.answer(
        "Oxirgi qadam: <b>Telefon raqamingizni</b> yuboring.\n\n"
        "Pastdagi <b>'📞 Kontaktni yuborish'</b> tugmasini bosing yoki qo'lda <code>+998901234567</code> ko'rinishida yozing:",
        reply_markup=get_contact_menu(),
        parse_mode="HTML"
    )

@router.message(SelfRegisterStates.phone, F.contact | F.text)
async def self_reg_phone_step(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Ro'yxatdan o'tish bekor qilindi. Qayta boshlash uchun /start ni bosing.")
        return

    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone = message.text.strip()
        if len(phone) < 7:
            await message.answer("Iltimos, to'g'ri telefon raqam kiriting yoki '📞 Kontaktni yuborish' tugmasini bosing:")
            return

    data = await state.get_data()
    full_name = data["full_name"]
    birth_date = data["birth_date"]
    tg_id = message.from_user.id

    member_id = await add_member(
        full_name=full_name,
        birth_date=birth_date,
        phone=phone,
        telegram_id=tg_id,
        role="member"
    )
    await state.clear()

    welcome_text = (
        f"🎉 <b>Tabriklaymiz, {full_name}!</b>\n\n"
        f"Siz kafedra fondi tizimiga muvaffaqiyatli a'zo bo'ldingiz.\n\n"
        f"📌 <b>Fond mezonlari:</b>\n"
        f"• Har oy majburiy badal: <b>50 000 so'm</b>\n"
        f"• Hamkasblar tug'ilgan kuni yig'imi: <b>25 000 so'm</b>\n"
        f"• Sizning tavallud ayyomingizda kafedra nomidan: <b>500 000 so'm</b> mukofot ajratiladi! 🎁\n\n"
        f"<i>Quyidagi menyu orqali to'lovlaringizni va kafedra fondi holatini kuzatib borishingiz mumkin:</i>"
    )
    await message.answer(welcome_text, reply_markup=get_member_menu(), parse_mode="HTML")

    # Adminlarga yangi a'zo haqida bildirishnoma
    admins = await get_all_admins()
    admin_tg_ids = {a["telegram_id"] for a in admins if a["telegram_id"]} | set(ADMIN_IDS)
    username_str = f"@{message.from_user.username}" if message.from_user.username else "mavjud emas"

    admin_notify = (
        f"🔔 <b>Yangi xodim o'zi ro'yxatdan o'tdi!</b>\n\n"
        f"👤 <b>F.I.SH:</b> {full_name}\n"
        f"🎂 <b>Tug'ilgan sana:</b> {birth_date}\n"
        f"📞 <b>Telefon:</b> {phone}\n"
        f"📱 <b>Telegram:</b> {username_str} (ID: <code>{tg_id}</code>)\n\n"
        f"<i>Xodim kafedra ro'yxatiga faol a'zo sifatida qo'shildi.</i>"
    )
    for adm_id in admin_tg_ids:
        if adm_id != tg_id:
            try:
                await bot.send_message(adm_id, admin_notify, parse_mode="HTML")
            except Exception:
                pass

# --- Mavjud profilni bog'lash ---
@router.callback_query(F.data == "show_unlinked_list")
async def show_unlinked_list_callback(callback: CallbackQuery):
    all_members = await get_all_members(active_only=True)
    unlinked_members = [m for m in all_members if not m["telegram_id"]]

    if not unlinked_members:
        await callback.answer("Hozirda bog'lanmagan profillar yo'q. Yangi ro'yxatdan o'ting.", show_alert=True)
        return

    buttons = []
    for m in unlinked_members[:10]:
        buttons.append([InlineKeyboardButton(text=f"👤 {m['full_name']}", callback_data=f"link_me:{m['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_reg_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Quyidagi ro'yxatdan o'z ism-familiyangizni tanlang:", reply_markup=kb)

@router.callback_query(F.data == "back_to_reg_menu")
async def back_to_reg_menu_callback(callback: CallbackQuery):
    all_members = await get_all_members(active_only=True)
    unlinked_members = [m for m in all_members if not m["telegram_id"]]

    buttons = [
        [InlineKeyboardButton(text="📝 Kafedra a'zosi sifatida ro'yxatdan o'tish", callback_data="start_self_register")]
    ]
    if unlinked_members:
        buttons.append([InlineKeyboardButton(text="🔗 Mening ismim oldin kiritilgan (Bog'lash)", callback_data="show_unlinked_list")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "Kafedra a'zosi sifatida qo'shilish uchun quyidagi <b>'Ro'yxatdan o'tish'</b> tugmasini bosing:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("link_me:"))
async def link_account_callback(callback: CallbackQuery):
    member_id = int(callback.data.split(":")[1])
    tg_id = callback.from_user.id

    member = await get_member_by_tg_id(tg_id)
    if member:
        await callback.answer("Siz allaqachon bog'langansiz!", show_alert=True)
        return

    await set_member_telegram_id(member_id, tg_id)
    target = await get_all_members()
    target_name = next((m["full_name"] for m in target if m["id"] == member_id), "Hurmatli xodim")

    await callback.message.delete()
    await callback.message.answer(
        f"✅ Tabriklaymiz, <b>{target_name}</b>!\n"
        f"Sizning Telegram profilingiz tizimga muvaffaqiyatli biriktirildi.",
        reply_markup=get_member_menu(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "close_menu")
async def close_menu_callback(callback: CallbackQuery):
    await callback.message.delete()

# --- Mening holatim va qarzlarim ---
@router.message(F.text == "💳 Mening to'lovlarim va qarzim")
async def my_debts_view(message: Message):
    tg_id = message.from_user.id
    member = await get_member_by_tg_id(tg_id)

    if not member:
        await message.answer("Siz tizimda biriktirilmagansiz. /start ni bosing.")
        return

    debts = await get_member_debts(member["id"])
    monthly_debts = debts["monthly_debts"]
    bday_debts = debts["birthday_debts"]
    total = debts["total_debt"]

    text_parts = [
        f"👤 <b>Xodim:</b> {member['full_name']}\n",
        f"🎂 <b>Tug'ilgan sana:</b> {member['birth_date']}\n\n",
        "📋 <b>TO'LOVLAR HOLATI:</b>\n"
    ]

    if total == 0:
        text_parts.append("🎉 <b>Sizda hech qanday qarzdorlik yo'q! Barcha badallar o'z vaqtida to'langan. Rahmat!</b>\n")
    else:
        text_parts.append(f"⚠️ <b>Jami to'lanishi kerak: {total:,} so'm</b>\n\n")

        if monthly_debts:
            text_parts.append("📅 <b>To'lanmagan oylik badallar (50 000 so'mdan):</b>\n")
            for d in monthly_debts:
                text_parts.append(f"  • {d['period_name']}: <b>{d['amount']:,} so'm</b>\n")
            text_parts.append("\n")

        if bday_debts:
            text_parts.append("🎂 <b>To'lanmagan tug'ilgan kun yig'imlari (25 000 so'mdan):</b>\n")
            for bd in bday_debts:
                text_parts.append(f"  • {bd['celebrant_name']} uchun: <b>{bd['amount']:,} so'm</b>\n")
            text_parts.append("\n")

        card_num = await get_setting("card_number", DEFAULT_CARD_NUMBER)
        card_holder = await get_setting("card_holder", DEFAULT_CARD_HOLDER)
        text_parts.append(f"💳 <b>To'lov uchun karta:</b>\n<code>{card_num}</code>\n({card_holder})\n")
        text_parts.append("<i>To'lov qilgach, chekni g'aznachiga taqdim eting.</i>")

    await message.answer("".join(text_parts), parse_mode="HTML")

# --- Fond balansi ---
@router.message(F.text == "💰 Fond balansi")
async def fund_balance_view(message: Message):
    stats = await get_fund_stats()
    balance = stats["balance"]
    members = await get_all_members(active_only=True)

    text = (
        f"🏛 <b>KAFEDRA FONDI HOLATI</b>\n\n"
        f"💰 <b>Kassadagi joriy qoldiq:</b> <code>{balance:,} so'm</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Jami tushumlar:</b> {stats['total_income']:,} so'm\n"
        f"  ├ Oylik badallardan: {stats['monthly_income']:,} so'm\n"
        f"  └ Tug'ilgan kun yig'imlaridan: {stats['birthday_income']:,} so'm\n\n"
        f"📤 <b>Jami xarajatlar:</b> {stats['total_expense']:,} so'm\n"
        f"  ├ Tug'ilgan kun mukofotlari: {stats['gifts_expense']:,} so'm\n"
        f"  └ Boshqa xarajatlar: {stats['other_expense']:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Kafedra a'zolari:</b> {len(members)} nafar\n"
        f"<i>Tizimdagi barcha hisob-kitoblar to'liq shaffof yuritiladi.</i>"
    )
    await message.answer(text, parse_mode="HTML")

# --- Tug'ilgan kunlar taqvimi ---
@router.message(F.text == "🎂 Tug'ilgan kunlar taqvimi")
@router.message(F.text == "🎂 Tug'ilgan kunlar")
async def birthdays_calendar_view(message: Message):
    upcoming = await get_upcoming_birthdays(limit_days=60)

    if not upcoming:
        await message.answer("Yaqin 2 oy ichida tug'ilgan kuni bo'lgan xodimlar yo'q yoki kiritilmagan.")
        return

    text_parts = ["🎂 <b>YAQINLASHIB KELAYOTGAN TUG'ILGAN KUNLAR:</b>\n\n"]
    for item in upcoming:
        m = item["member"]
        days = item["days_left"]
        target = item["target_date"]

        if days == 0:
            status_str = "🎉 <b>BUGUN!</b> (Tavallud ayyom)"
        elif days == 1:
            status_str = "⏳ <b>Ertaga!</b>"
        else:
            status_str = f"📅 {days} kundan keyin ({target})"

        text_parts.append(
            f"👤 <b>{m['full_name']}</b>\n"
            f"   └ Holati: {status_str}\n"
        )

    text_parts.append("\n<i>Eslatma: Har bir xodimning tug'ilgan kuniga qolganlardan 25 000 so'mdan yig'iladi va xodimga 500 000 so'm mukofot topshiriladi.</i>")
    await message.answer("".join(text_parts), parse_mode="HTML")

# --- To'lov rekvizitlari ---
@router.message(F.text == "ℹ️ To'lov rekvizitlari")
async def payment_details_view(message: Message):
    card_num = await get_setting("card_number", DEFAULT_CARD_NUMBER)
    card_holder = await get_setting("card_holder", DEFAULT_CARD_HOLDER)

    text = (
        f"💳 <b>KAFEDRA FONDI TO'LOV MA'LUMOTLARI</b>\n\n"
        f"Karta raqami:\n<code>{card_num}</code>\n"
        f"Karta egasi: <b>{card_holder}</b>\n\n"
        f"📌 <b>Fond qoidalari:</b>\n"
        f"• Har oylik majburiy badal: <b>50 000 so'm</b>\n"
        f"• Hamkasbning tug'ilgan kuni uchun yig'im: <b>25 000 so'm</b>\n"
        f"• Tug'ilgan kun nishonlayotgan xodimga mukofot: <b>500 000 so'm</b>\n\n"
        f"<i>To'lov qilgach, chekni g'aznachiga taqdim etishingizni so'raymiz.</i>"
    )
    await message.answer(text, parse_mode="HTML")
