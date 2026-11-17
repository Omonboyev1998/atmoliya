from datetime import datetime, date
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    is_admin,
    make_admin,
    add_member,
    get_all_members,
    get_member_by_id,
    delete_member,
    get_all_debtors,
    get_member_debts,
    generate_monthly_dues,
    mark_monthly_due_paid,
    mark_birthday_due_paid,
    give_birthday_gift,
    add_custom_transaction,
    get_fund_stats,
    get_setting,
    set_setting,
    trigger_birthday_event,
    get_upcoming_birthdays
)
from config import ADMIN_PASSWORD
from keyboards.default import get_admin_menu, get_cancel_menu
from keyboards.inline import (
    get_members_keyboard,
    get_member_due_selection_keyboard,
    get_confirm_keyboard,
    get_debt_remind_keyboard,
    get_settings_keyboard,
    get_birthday_gift_keyboard
)
from services.excel_service import generate_financial_report

router = Router()

class AddMemberForm(StatesGroup):
    full_name = State()
    birth_date = State()
    phone = State()

class AddExpenseForm(StatesGroup):
    amount = State()
    description = State()

class CardSettingForm(StatesGroup):
    card_number = State()
    card_holder = State()

# --- Adminlikni faollashtirish (Login) ---
@router.message(F.text.startswith("/admin"))
async def admin_auth_handler(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        if await is_admin(message.from_user.id):
            await message.answer("👑 Siz allaqachon Admin / G'aznachisiz!", reply_markup=get_admin_menu())
        else:
            await message.answer(
                "🔐 <b>G'aznachi (Admin) paneliga kirish:</b>\n\n"
                "Iltimos, maxsus parolni birga yuboring:\n"
                "<i>Masalan:</i> <code>/admin kafedra777</code>",
                parse_mode="HTML"
            )
        return

    entered_pass = parts[1].strip()
    if entered_pass == ADMIN_PASSWORD:
        await make_admin(message.from_user.id, message.from_user.full_name)
        await message.answer(
            f"👑 <b>Xush kelibsiz, {message.from_user.full_name}!</b>\n\n"
            f"Siz muvaffaqiyatli <b>Admin / G'aznachi</b> maqomiga ega bo'ldingiz.\n"
            f"Endi kafedra a'zolari oddiy xodim sifatida kiradi, siz esa fondni boshqarasiz.",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Noto'g'ri parol! Qaytadan urinib ko'ring.")

# --- Bekor qilish ---
@router.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Amal bekor qilindi.", reply_markup=get_admin_menu())

# --- 1. Xodimlar ro'yxati ---
@router.message(F.text == "👥 Xodimlar")
async def list_members_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return

    members = await get_all_members(active_only=True)
    if not members:
        await message.answer("Hozircha xodimlar kiritilmagan. '➕ Yangi xodim qo'shish' tugmasini bosing.")
        return

    text = f"👥 <b>Kafedra xodimlari ro'yxati ({len(members)} nafar):</b>\n\nBatafsil ma'lumot yoki boshqarish uchun xodimni tanlang:"
    kb = get_members_keyboard(members, action_prefix="view_member")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("view_member_page:"))
async def paginate_members(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    members = await get_all_members(active_only=True)
    kb = get_members_keyboard(members, action_prefix="view_member", page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)

@router.callback_query(F.data.startswith("view_member:"))
async def view_single_member(callback: CallbackQuery):
    member_id = int(callback.data.split(":")[1])
    m = await get_member_by_id(member_id)
    if not m:
        await callback.answer("Xodim topilmadi!")
        return

    debts = await get_member_debts(member_id)
    tg_status = "✅ Bog'langan" if m["telegram_id"] else "❌ Bog'lanmagan"

    text = (
        f"👤 <b>F.I.SH:</b> {m['full_name']}\n"
        f"🎂 <b>Tug'ilgan sana:</b> {m['birth_date']}\n"
        f"📞 <b>Telefon:</b> {m.get('phone') or 'Kiritilmagan'}\n"
        f"📱 <b>Telegram:</b> {tg_status}\n"
        f"🎖 <b>Roli:</b> {m['role'].capitalize()}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Joriy qarzdorlik:</b> {debts['total_debt']:,} so'm\n"
    )

    buttons = [
        [InlineKeyboardButton(text="💵 To'lov yozish", callback_data=f"pay_for_member:{member_id}")],
        [InlineKeyboardButton(text="🗑 Xodimni o'chirish", callback_data=f"ask_delete_member:{member_id}")],
        [InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="back_to_members")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "back_to_members")
async def back_to_members_list(callback: CallbackQuery):
    members = await get_all_members(active_only=True)
    kb = get_members_keyboard(members, action_prefix="view_member")
    await callback.message.edit_text("👥 <b>Kafedra xodimlari ro'yxati:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("ask_delete_member:"))
async def ask_delete_member_callback(callback: CallbackQuery):
    member_id = int(callback.data.split(":")[1])
    m = await get_member_by_id(member_id)
    text = f"Haqiqatan ham <b>{m['full_name']}</b>ni kafedra ro'yxatidan o'chirmoqchimisiz?"
    await callback.message.edit_text(text, reply_markup=get_confirm_keyboard("delete_member", member_id), parse_mode="HTML")

@router.callback_query(F.data.startswith("confirm_delete_member:"))
async def confirm_delete_member_callback(callback: CallbackQuery):
    member_id = int(callback.data.split(":")[1])
    await delete_member(member_id)
    await callback.answer("Xodim ro'yxatdan o'chirildi!", show_alert=True)
    await back_to_members_list(callback)

# --- 2. Yangi xodim qo'shish ---
@router.message(F.text == "➕ Yangi xodim qo'shish")
async def add_member_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return

    await state.set_state(AddMemberForm.full_name)
    await message.answer(
        "Yangi xodimning <b>Familiyasi, Ismi va Sharifini</b> kiriting:\n<i>(Masalan: Karimov Alisher Baxtiyorovich)</i>",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML"
    )

@router.message(AddMemberForm.full_name)
async def add_member_name_step(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("Iltimos, to'liq ism-familiyani kiriting:")
        return

    await state.update_data(full_name=name)
    await state.set_state(AddMemberForm.birth_date)
    await message.answer(
        f"<b>{name}</b>ning tug'ilgan sanasini kiriting:\n<i>Format: KK.OO.YYYY (Masalan: 18.05.1985)</i>",
        parse_mode="HTML"
    )

@router.message(AddMemberForm.birth_date)
async def add_member_bday_step(message: Message, state: FSMContext):
    bday_text = message.text.strip()
    parts = bday_text.split(".")
    if len(parts) < 2:
        await message.answer("Noto'g'ri format! Iltimos, <b>KK.OO.YYYY</b> yoki <b>KK.OO</b> formatida kiriting (Masalan: 25.10.1990):", parse_mode="HTML")
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
    await state.set_state(AddMemberForm.phone)
    await message.answer(
        "Xodimning <b>telefon raqamini</b> kiriting (yoki o'tkazib yuborish uchun '-' deb yozing):\n<i>Masalan: +998901234567</i>",
        parse_mode="HTML"
    )

@router.message(AddMemberForm.phone)
async def add_member_phone_step(message: Message, state: FSMContext):
    phone_text = message.text.strip()
    phone = None if phone_text == "-" else phone_text

    data = await state.get_data()
    member_id = await add_member(
        full_name=data["full_name"],
        birth_date=data["birth_date"],
        phone=phone
    )
    await state.clear()

    await message.answer(
        f"✅ <b>Xodim muvaffaqiyatli qo'shildi!</b>\n\n"
        f"👤 <b>F.I.SH:</b> {data['full_name']}\n"
        f"🎂 <b>Tug'ilgan sana:</b> {data['birth_date']}\n"
        f"📞 <b>Telefon:</b> {phone or 'Kiritilmadi'}\n\n"
        f"<i>Xodim botga kirganda o'z ismini tanlab o'z profilini Telegramiga ulab oladi.</i>",
        reply_markup=get_admin_menu(),
        parse_mode="HTML"
    )

# --- 3. To'lov qabul qilish ---
@router.message(F.text == "💵 To'lov qabul qilish")
async def collect_payment_start(message: Message):
    if not await is_admin(message.from_user.id):
        return

    debtors = await get_all_debtors()
    if debtors:
        text = "💵 <b>To'lov qabul qilish uchun qarzdor xodimni tanlang:</b>"
        members_list = [d["member"] for d in debtors]
    else:
        text = "💵 <b>To'lov kiritish uchun xodimni tanlang:</b>\n<i>(Hozirda barcha qarzdorliklar yopilgan)</i>"
        members_list = await get_all_members(active_only=True)

    kb = get_members_keyboard(members_list, action_prefix="pay_for_member")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("pay_for_member_page:"))
async def paginate_pay_members(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    debtors = await get_all_debtors()
    members_list = [d["member"] for d in debtors] if debtors else await get_all_members(active_only=True)
    kb = get_members_keyboard(members_list, action_prefix="pay_for_member", page=page)
    await callback.message.edit_reply_markup(reply_markup=kb)

@router.callback_query(F.data.startswith("pay_for_member:"))
async def select_member_for_payment(callback: CallbackQuery):
    member_id = int(callback.data.split(":")[1])
    m = await get_member_by_id(member_id)
    if not m:
        await callback.answer("Xodim topilmadi!")
        return

    debts = await get_member_debts(member_id)
    monthly_debts = debts["monthly_debts"]
    bday_debts = debts["birthday_debts"]

    text = (
        f"👤 <b>Xodim:</b> {m['full_name']}\n"
        f"⚠️ <b>Jami qarzdorlik:</b> {debts['total_debt']:,} so'm\n\n"
        f"<i>Qaysi badal to'langanini belgilash uchun tugmani bosing:</i>"
    )
    kb = get_member_due_selection_keyboard(member_id, monthly_debts, bday_debts)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("pay_monthly:"))
async def process_monthly_payment(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    due_id = int(parts[1])
    member_id = int(parts[2])

    success = await mark_monthly_due_paid(due_id)
    if success:
        m = await get_member_by_id(member_id)
        await callback.answer("✅ 50 000 so'm oylik badal to'landi!", show_alert=True)

        # Xodimga Telegram orqali xushxabar yuborish
        if m and m["telegram_id"]:
            try:
                await bot.send_message(
                    m["telegram_id"],
                    f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                    f"Hurmatli {m['full_name']}, sizning kafedra fondiga <b>50 000 so'm</b> oylik badal to'lovingiz qabul qilindi. Rahmat!",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # Menuni yangilash
        debts = await get_member_debts(member_id)
        text = (
            f"👤 <b>Xodim:</b> {m['full_name']}\n"
            f"✅ <b>50 000 so'm oylik badal qabul qilindi va kassa kirimiga yozildi!</b>\n\n"
            f"⚠️ <b>Qolgan qarz:</b> {debts['total_debt']:,} so'm"
        )
        kb = get_member_due_selection_keyboard(member_id, debts["monthly_debts"], debts["birthday_debts"])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.answer("Bu to'lov allaqachon to'langan!", show_alert=True)

@router.callback_query(F.data.startswith("pay_bday:"))
async def process_bday_payment(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    due_id = int(parts[1])
    member_id = int(parts[2])

    success = await mark_birthday_due_paid(due_id)
    if success:
        m = await get_member_by_id(member_id)
        await callback.answer("✅ 25 000 so'm tug'ilgan kun yig'imi to'landi!", show_alert=True)

        if m and m["telegram_id"]:
            try:
                await bot.send_message(
                    m["telegram_id"],
                    f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                    f"Hurmatli {m['full_name']}, sizning tug'ilgan kun uchun <b>25 000 so'm</b> yig'im to'lovingiz qabul qilindi. Rahmat!",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        debts = await get_member_debts(member_id)
        text = (
            f"👤 <b>Xodim:</b> {m['full_name']}\n"
            f"✅ <b>25 000 so'm tug'ilgan kun yig'imi qabul qilindi va kassa kirimiga yozildi!</b>\n\n"
            f"⚠️ <b>Qolgan qarz:</b> {debts['total_debt']:,} so'm"
        )
        kb = get_member_due_selection_keyboard(member_id, debts["monthly_debts"], debts["birthday_debts"])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.answer("Bu to'lov allaqachon to'langan!", show_alert=True)

# --- 4. Chiqim kiritish ---
@router.message(F.text == "💸 Chiqim kiritish")
async def add_expense_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return

    await state.set_state(AddExpenseForm.amount)
    await message.answer(
        "Chiqim summasini so'mda kiriting:\n<i>(Masalan: 150000 yoki 500000)</i>",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML"
    )

@router.message(AddExpenseForm.amount)
async def add_expense_amount_step(message: Message, state: FSMContext):
    clean_text = message.text.replace(" ", "").replace(",", "").replace("so'm", "").replace("som", "")
    if not clean_text.isdigit() or int(clean_text) <= 0:
        await message.answer("Iltimos, to'g'ri musbat raqam kiriting (Masalan: 120000):")
        return

    amount = int(clean_text)
    await state.update_data(amount=amount)
    await state.set_state(AddExpenseForm.description)
    await message.answer(
        f"Summa: <b>{amount:,} so'm</b>\n\nChiqim maqsadi / izohini kiriting:\n<i>(Masalan: Kafedra uchun kanselyariya xaridi, bayram dasturxoni va h.k.)</i>",
        parse_mode="HTML"
    )

@router.message(AddExpenseForm.description)
async def add_expense_desc_step(message: Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    amount = data["amount"]

    await add_custom_transaction(
        tx_type="expense",
        category="other_expense",
        amount=amount,
        description=desc
    )
    await state.clear()

    stats = await get_fund_stats()
    await message.answer(
        f"✅ <b>Chiqim kassaga muvaffaqiyatli kiritildi!</b>\n\n"
        f"📤 <b>Chiqim summasi:</b> {amount:,} so'm\n"
        f"📝 <b>Maqsad:</b> {desc}\n"
        f"💰 <b>Kassada qolgan balans:</b> {stats['balance']:,} so'm",
        reply_markup=get_admin_menu(),
        parse_mode="HTML"
    )

# --- 5. Qarzdorlar ro'yxati ---
@router.message(F.text == "⚠️ Qarzdorlar ro'yxati")
async def debtor_list_view(message: Message):
    if not await is_admin(message.from_user.id):
        return

    debtors = await get_all_debtors()
    if not debtors:
        await message.answer("🎉 <b>Barcha xodimlarning qarzlari to'liq yopilgan!</b> Hozirda hech kimda qarzdorlik yo'q.", parse_mode="HTML")
        return

    total_all_debt = sum(d["debts"]["total_debt"] for d in debtors)
    text_parts = [
        f"⚠️ <b>QARZDOR XODIMLAR RO'YXATI ({len(debtors)} nafar):</b>\n",
        f"Umumiy undirilishi kerak bo'lgan summa: <b>{total_all_debt:,} so'm</b>\n\n"
    ]

    for idx, d in enumerate(debtors, 1):
        m = d["member"]
        debts = d["debts"]
        monthly_count = len(debts["monthly_debts"])
        bday_count = len(debts["birthday_debts"])

        details = []
        if monthly_count:
            details.append(f"{monthly_count} ta oylik ({monthly_count * 50_000:,} so'm)")
        if bday_count:
            details.append(f"{bday_count} ta t-kun ({bday_count * 25_000:,} so'm)")

        details_str = ", ".join(details)
        tg_icon = "📱" if m["telegram_id"] else "📵"

        text_parts.append(
            f"{idx}. <b>{m['full_name']}</b> {tg_icon}\n"
            f"   └ Qarz: <b>{debts['total_debt']:,} so'm</b> ({details_str})\n"
        )

    text_parts.append("\n<i>To'lovlarni qabul qilish uchun '💵 To'lov qabul qilish' tugmasidan foydalaning.</i>")

    buttons = [
        [InlineKeyboardButton(text="📢 Barcha qarzdorlarga eslatma yuborish", callback_data="broadcast_debt_reminder")],
        [InlineKeyboardButton(text="📊 Excel hisobotni olish", callback_data="get_excel_report")]
    ]
    await message.answer("".join(text_parts), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "broadcast_debt_reminder")
async def broadcast_debt_reminder_callback(callback: CallbackQuery, bot: Bot):
    debtors = await get_all_debtors()
    card_num = await get_setting("card_number", "8600 0000 0000 0000")
    card_holder = await get_setting("card_holder", "Kafedra G'aznachisi")

    sent_count = 0
    not_sent_count = 0

    for d in debtors:
        m = d["member"]
        debts = d["debts"]
        if m["telegram_id"]:
            msg = (
                f"Hurmatli <b>{m['full_name']}</b>!\n\n"
                f"Kafedra fondi bo'yicha jami qarzdorligingiz: <b>{debts['total_debt']:,} so'm</b>.\n"
                f"Iltimos, badal to'lovlarini o'z vaqtida amalga oshirishingizni so'raymiz.\n\n"
                f"💳 <b>Karta:</b> <code>{card_num}</code> ({card_holder})\n\n"
                f"<i>To'lov qilganingizdan so'ng g'aznachiga xabar bering. Rahmat!</i>"
            )
            try:
                await bot.send_message(m["telegram_id"], msg, parse_mode="HTML")
                sent_count += 1
            except Exception:
                not_sent_count += 1
        else:
            not_sent_count += 1

    await callback.answer(f"Xabarnoma yuborildi!\nYetkazildi: {sent_count} ta\nYetkazilmadi (Telegram ulanmagan): {not_sent_count} ta", show_alert=True)

# --- 6. Excel hisobot ---
@router.message(F.text == "📊 Excel hisobot")
@router.callback_query(F.data == "get_excel_report")
async def send_excel_report(event: Message | CallbackQuery):
    msg = event if isinstance(event, Message) else event.message
    waiting_msg = await msg.answer("⏳ Excel hisobot tayyorlanmoqda, iltimos kuting...")

    try:
        file_path = await generate_financial_report()
        doc = FSInputFile(file_path)
        stats = await get_fund_stats()

        caption = (
            f"📊 <b>KAFEDRA FONDI MOLIYAVIY HISOBOTI</b>\n\n"
            f"💰 Kassadagi qoldiq: <b>{stats['balance']:,} so'm</b>\n"
            f"📥 Jami tushum: {stats['total_income']:,} so'm\n"
            f"📤 Jami xarajat: {stats['total_expense']:,} so'm\n\n"
            f"<i>Faylda barcha xodimlarning badallari, qarzlar va kassa jurnali to'liq aks etgan.</i>"
        )
        await msg.answer_document(doc, caption=caption, parse_mode="HTML")
        await waiting_msg.delete()
    except Exception as e:
        await waiting_msg.edit_text(f"Xatolik yuz berdi: {e}")

# --- 7. Yangi oy badalini ochish ---
@router.message(F.text == "📅 Yangi oy badalini ochish")
async def trigger_new_month_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return

    today = date.today()
    period_name = await generate_monthly_dues(today.year, today.month)
    members = await get_all_members(active_only=True)

    await message.answer(
        f"✅ <b>{period_name} uchun oylik badal muvaffaqiyatli shakllantirildi!</b>\n\n"
        f"Kafedraning barcha {len(members)} nafar faol a'zolariga <b>50 000 so'mdan</b> majburiy badal yozildi.",
        parse_mode="HTML"
    )

# --- 8. Tug'ilgan kun sovg'asi topshirish ---
@router.callback_query(F.data.startswith("give_gift:"))
async def give_gift_callback(callback: CallbackQuery, bot: Bot):
    event_id = int(callback.data.split(":")[1])
    success = await give_birthday_gift(event_id)
    if success:
        await callback.answer("🎁 500 000 so'm mukofot topshirildi deb belgilandi va chiqimga yozildi!", show_alert=True)
        stats = await get_fund_stats()
        await callback.message.edit_text(
            f"✅ <b>500 000 so'm mukofot chiqim qilindi!</b>\n"
            f"💰 Kassada qolgan summa: {stats['balance']:,} so'm",
            parse_mode="HTML"
        )
    else:
        await callback.answer("Bu mukofot allaqachon berilgan!", show_alert=True)

# --- 9. Sozlamalar ---
@router.message(F.text == "⚙️ Sozlamalar")
async def settings_view(message: Message):
    if not await is_admin(message.from_user.id):
        return

    card_num = await get_setting("card_number", "8600 0000 0000 0000")
    card_holder = await get_setting("card_holder", "Kafedra G'aznachisi")

    text = (
        f"⚙️ <b>FONDI TIZIMI SOZLAMALARI:</b>\n\n"
        f"💳 <b>Karta:</b> <code>{card_num}</code>\n"
        f"👤 <b>Karta egasi:</b> {card_holder}\n"
        f"💵 <b>Oylik badal:</b> 50 000 so'm\n"
        f"🎂 <b>Tug'ilgan kun badali:</b> 25 000 so'm\n"
        f"🎁 <b>Tug'ilgan kun mukofoti:</b> 500 000 so'm\n"
    )
    await message.answer(text, reply_markup=get_settings_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "set_card")
async def set_card_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CardSettingForm.card_number)
    await callback.message.answer(
        "Yangi karta raqamini kiriting:\n<i>(Masalan: 9860 1234 5678 9012)</i>",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(CardSettingForm.card_number)
async def set_card_number_step(message: Message, state: FSMContext):
    card_num = message.text.strip()
    await state.update_data(card_number=card_num)
    await state.set_state(CardSettingForm.card_holder)
    await message.answer("Karta egasining ism-sharifini kiriting:\n<i>(Masalan: Alisher K.)</i>", parse_mode="HTML")

@router.message(CardSettingForm.card_holder)
async def set_card_holder_step(message: Message, state: FSMContext):
    holder = message.text.strip()
    data = await state.get_data()
    card_num = data["card_number"]

    await set_setting("card_number", card_num)
    await set_setting("card_holder", holder)
    await state.clear()

    await message.answer(
        f"✅ <b>Karta ma'lumotlari yangilandi!</b>\n\n"
        f"💳 Karta: <code>{card_num}</code>\n"
        f"👤 Egasi: {holder}",
        reply_markup=get_admin_menu(),
        parse_mode="HTML"
    )
