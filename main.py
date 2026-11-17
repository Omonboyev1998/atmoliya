import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from config import BOT_TOKEN, PORT
from database.db import init_db
from handlers.common import router as common_router
from handlers.admin import router as admin_router
from services.scheduler import setup_scheduler
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def start_web_healthcheck(port: int):
    async def ping_handler(request):
        return web.Response(text="Kafedra Fondi Telegram Bot is running!")

    app = web.Application()
    app.router.add_get("/", ping_handler)
    app.router.add_get("/health", ping_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Render health-check server ishga tushdi (Port: {port})")

async def main():
    if not BOT_TOKEN or "YOUR_TOKEN" in BOT_TOKEN:
        logger.error("BOT_TOKEN ko'rsatilmagan! .env faylini tekshiring.")
        return

    logger.info("Ma'lumotlar bazasi ishga tushirilmoqda...")
    await init_db()

    # Agar Render PORT bergan bo'lsa, health-check veb-serverini ishga tushirish
    if PORT > 0:
        await start_web_healthcheck(PORT)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Routerlarni ulash
    dp.include_router(common_router)
    dp.include_router(admin_router)

    # Bot buyruqlari
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni qayta ishga tushirish / Bosh sahifa")
    ])

    # Avtomatlashtirilgan rejalashtiruvchini ishga tushirish
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler muvaffaqiyatli ishga tushirildi.")

    logger.info("Kafedra fondi boti ishga tushdi!")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
