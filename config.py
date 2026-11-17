import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "9000286520:AAG-vLu8u4B5bWZhpJsxf3kYFGlhvVfv_Y4")

# Admin telegram ID larini vergul bilan ajratib kiritish mumkin
raw_admin_ids = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(i.strip()) for i in raw_admin_ids.split(",") if i.strip().isdigit()]

# Admin bo'lish uchun maxsus parol (botda /admin <parol> yoziladi)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kafedra777")

# Standart moliyaviy mezonlar (so'mda)
DEFAULT_MONTHLY_FEE = 50_000
DEFAULT_BIRTHDAY_FEE = 25_000
DEFAULT_BIRTHDAY_GIFT = 500_000

# Rekvizitlar
DEFAULT_CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 0000 0000 0000")
DEFAULT_CARD_HOLDER = os.getenv("CARD_HOLDER", "Kafedra G'aznachisi")

# Turso Database (LibSQL) sozlamalari
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

# Render yoki server porti
PORT = int(os.getenv("PORT", "0") or "0")

# Database fayli (agar Turso ulanmagan bo'lsa lokal SQLite ishlatiladi)
DB_PATH = BASE_DIR / "database" / "fund.db"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
