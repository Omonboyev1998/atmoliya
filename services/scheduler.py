import logging
from datetime import datetime, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from database.db import (
    get_upcoming_birthdays,
    trigger_birthday_event,
    get_all_members,
    generate_monthly_dues,
    get_connection,
    ADMIN_IDS
)
from keyboards.inline import get_birthday_gift_keyboard

logger = logging.getLogger(__name__)

async def daily_birthday_check(bot: Bot):
    logger.info("Kunlik tug'ilgan kunlar tekshiruvi boshlandi...")
    today = date.today()
    upcoming = await get_upcoming_birthdays(limit_days=3)
    members = await get_all_members(active_only=True)

    for item in upcoming:
        m = item["member"]
        days = item["days_left"]

        # Tug'ilgan kunga 3 kun qolganda yoki bugun bo'lsa, tadbir ochish
        event_id = await trigger_birthday_event(member_id=m["id"], year=today.year)

        if days == 3:
            # 3 kun oldin ogohlantirish
            text = (
                f"🎂 <b>DIQQAT: TAVALLUD AYYOM YAQINLASHMOQDA!</b>\n\n"
                f"3 kundan keyin (<b>{item['target_date']}</b>) kafedramiz xodimi <b>{m['full_name']}</b> o'z tavallud ayyomini nishonlaydi!\n\n"
                f"📌 Qolgan barcha xodimlardan: <b>25 000 so'mdan</b> yig'iladi.\n"
                f"🎁 Tug'ilgan kun egasiga kafedra nomidan <b>500 000 so'm</b> mukofot topshiriladi."
            )
            for mem in members:
                if mem["telegram_id"]:
                    try:
                        await bot.send_message(mem["telegram_id"], text, parse_mode="HTML")
                    except Exception:
                        pass

        elif days == 0:
            # Bugun - Tabrik va adminlarga mukofot berish eslatmasi
            text = (
                f"🎉 <b>BUGUN KAFEDRAMIZDA BAYRAM!</b> 🎉\n\n"
                f"Bugun kafedramizning hurmatli a'zosi <b>{m['full_name']}</b> o'z tavallud ayyomini nishonlamoqda!\n\n"
                f"Kafedramiz jamoasi nomidan mustahkam sog'liq, oilaviy baxt va ilmiy-pedagogik faoliyatlarida ulkan zafarlar tilaymiz! 💐"
            )
            for mem in members:
                if mem["telegram_id"]:
                    try:
                        await bot.send_message(mem["telegram_id"], text, parse_mode="HTML")
                    except Exception:
                        pass

            # Adminlarga 500 000 so'm topshirish tugmasini yuborish
            with get_connection() as conn:
                ev = conn.execute("SELECT gift_given FROM birthday_events WHERE id = ?", (event_id,)).fetchone()
                gift_given = ev["gift_given"] if ev else 0

            admin_text = (
                f"👑 <b>Adminlar diqqatiga:</b>\n"
                f"Bugun <b>{m['full_name']}</b>ning tug'ilgan kuni.\n"
                f"Fond hisobidan <b>500 000 so'm</b> mukofot topshirildimi?"
            )
            kb = get_birthday_gift_keyboard(event_id, bool(gift_given))
            for mem in members:
                if mem["role"] == "admin" and mem["telegram_id"]:
                    try:
                        await bot.send_message(mem["telegram_id"], admin_text, reply_markup=kb, parse_mode="HTML")
                    except Exception:
                        pass
            for adm_id in ADMIN_IDS:
                try:
                    await bot.send_message(adm_id, admin_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass

async def monthly_fee_generation(bot: Bot):
    logger.info("Oylik badallar shakllantirilmoqda...")
    today = date.today()
    period_name = await generate_monthly_dues(today.year, today.month)
    members = await get_all_members(active_only=True)

    text = (
        f"📅 <b>YANGI OY BADALI!</b>\n\n"
        f"Hurmatli kafedra a'zolari, <b>{period_name}</b> uchun kafedra fondiga <b>50 000 so'mlik</b> majburiy badal ochildi.\n\n"
        f"Iltimos, badal to'lovini g'aznachiga topshirishingizni so'raymiz."
    )
    for mem in members:
        if mem["telegram_id"]:
            try:
                await bot.send_message(mem["telegram_id"], text, parse_mode="HTML")
            except Exception:
                pass

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

    # Har kuni ertalab 09:00 da tug'ilgan kunlarni tekshirish
    scheduler.add_job(daily_birthday_check, "cron", hour=9, minute=0, args=[bot])

    # Har oyning 1-sanasida soat 00:05 da oylik badal yaratish
    scheduler.add_job(monthly_fee_generation, "cron", day=1, hour=0, minute=5, args=[bot])

    return scheduler
