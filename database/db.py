import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from config import (
    DB_PATH,
    DEFAULT_MONTHLY_FEE,
    DEFAULT_BIRTHDAY_FEE,
    DEFAULT_BIRTHDAY_GIFT,
    ADMIN_IDS,
    TURSO_DATABASE_URL,
    TURSO_AUTH_TOKEN,
    FUND_START_YEAR,
    FUND_START_MONTH
)

class CursorWrapper:
    def __init__(self, cur):
        self.cur = cur
        self.lastrowid = getattr(cur, "lastrowid", None)

    def _convert_row(self, row):
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return dict(row)
        if isinstance(row, dict):
            return row
        if isinstance(row, (list, tuple)) and self.cur.description:
            cols = [d[0] for d in self.cur.description]
            return dict(zip(cols, row))
        return row

    def fetchone(self):
        row = self.cur.fetchone()
        return self._convert_row(row)

    def fetchall(self):
        rows = self.cur.fetchall()
        return [self._convert_row(r) for r in rows]

class ConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return CursorWrapper(cur)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        self.close()

def get_connection():
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        import libsql
        raw_conn = libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
        return ConnectionWrapper(raw_conn)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        raw_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        raw_conn.row_factory = sqlite3.Row
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        return ConnectionWrapper(raw_conn)

async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # Xodimlar jadvali
        conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            full_name TEXT NOT NULL,
            phone TEXT,
            birth_date TEXT NOT NULL, -- DD.MM.YYYY
            birth_day_month TEXT NOT NULL, -- MM-DD
            role TEXT DEFAULT 'member', -- 'admin', 'member'
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Oylik davrlar (masalan: 2026-11)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS monthly_periods (
            period TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Oylik badallar
        conn.execute("""
        CREATE TABLE IF NOT EXISTS monthly_dues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL REFERENCES monthly_periods(period) ON DELETE CASCADE,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL DEFAULT 50000,
            status TEXT DEFAULT 'unpaid', -- 'unpaid', 'paid'
            paid_at TIMESTAMP,
            UNIQUE(period, member_id)
        );
        """)

        # Tug'ilgan kun hodisalari
        conn.execute("""
        CREATE TABLE IF NOT EXISTS birthday_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            event_year INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            gift_amount INTEGER DEFAULT 500000,
            gift_given INTEGER DEFAULT 0,
            gift_given_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(member_id, event_year)
        );
        """)

        # Tug'ilgan kun uchun qolgan xodimlardan 25 minglik yig'im
        conn.execute("""
        CREATE TABLE IF NOT EXISTS birthday_dues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES birthday_events(id) ON DELETE CASCADE,
            payer_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL DEFAULT 25000,
            status TEXT DEFAULT 'unpaid', -- 'unpaid', 'paid'
            paid_at TIMESTAMP,
            UNIQUE(event_id, payer_id)
        );
        """)

        # Kassa jurnali (Barcha kirim va chiqimlar)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, -- 'income' (kirim), 'expense' (chiqim)
            category TEXT NOT NULL, -- 'monthly_fee', 'birthday_fee', 'birthday_gift', 'other_income', 'other_expense'
            amount INTEGER NOT NULL,
            member_id INTEGER REFERENCES members(id) ON DELETE SET NULL,
            related_id INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Sozlamalar jadvali
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        conn.commit()

    # Fond boshlangan (01.09.2026) dan to bugungacha bo'lgan barcha oylarni tayyorlash
    await ensure_active_periods()

async def ensure_active_periods():
    today = date.today()
    cur_y, cur_m = FUND_START_YEAR, FUND_START_MONTH
    while (cur_y < today.year) or (cur_y == today.year and cur_m <= today.month):
        await generate_monthly_dues(cur_y, cur_m)
        cur_m += 1
        if cur_m > 12:
            cur_m = 1
            cur_y += 1

# --- Xodimlar bo'yicha funksiyalar ---

def parse_day_month(birth_date_str: str) -> str:
    """Format: DD.MM.YYYY yoki DD.MM -> MM-DD qaytaradi"""
    parts = birth_date_str.strip().split(".")
    day = int(parts[0])
    month = int(parts[1])
    return f"{month:02d}-{day:02d}"

async def add_member(full_name: str, birth_date: str, phone: str = None, telegram_id: int = None, role: str = "member") -> int:
    day_month = parse_day_month(birth_date)
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO members (telegram_id, full_name, phone, birth_date, birth_day_month, role)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (telegram_id, full_name, phone, birth_date, day_month, role))
        member_id = cursor.lastrowid

        # Fond hisobi boshlanganidan (01.09.2026) buyon mavjud bo'lgan barcha oylar uchun badal yozish
        periods = conn.execute("SELECT period FROM monthly_periods").fetchall()
        for p in periods:
            conn.execute("""
                INSERT OR IGNORE INTO monthly_dues (period, member_id, amount, status)
                VALUES (?, ?, ?, 'unpaid')
            """, (p["period"], member_id, DEFAULT_MONTHLY_FEE))

        conn.commit()
        return member_id

async def get_all_admins() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM members WHERE role = 'admin' AND is_active = 1").fetchall()
        return [dict(row) for row in rows]

async def get_all_members(active_only: bool = True) -> List[Dict[str, Any]]:
    query = "SELECT * FROM members"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY full_name ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]

async def get_member_by_id(member_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        return dict(row) if row else None

async def get_member_by_tg_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE telegram_id = ? AND is_active = 1", (telegram_id,)).fetchone()
        return dict(row) if row else None

async def set_member_telegram_id(member_id: int, telegram_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE members SET telegram_id = ? WHERE id = ?", (telegram_id, member_id))
        conn.commit()

async def delete_member(member_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE members SET is_active = 0 WHERE id = ?", (member_id,))
        conn.commit()

async def is_admin(telegram_id: int) -> bool:
    if telegram_id in ADMIN_IDS:
        return True
    with get_connection() as conn:
        row = conn.execute("SELECT role FROM members WHERE telegram_id = ? AND is_active = 1", (telegram_id,)).fetchone()
        if row and row["role"] == "admin":
            return True
        # Sozlamalardan tekshirish
        admin_setting = conn.execute("SELECT value FROM settings WHERE key = 'admin_ids'").fetchone()
        if admin_setting:
            stored_ids = [int(i.strip()) for i in admin_setting["value"].split(",") if i.strip().isdigit()]
            if telegram_id in stored_ids:
                return True
    return False

async def make_admin(telegram_id: int, full_name: str = "Kafedra G'aznachisi"):
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM members WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row:
            conn.execute("UPDATE members SET role = 'admin' WHERE id = ?", (row["id"],))
        else:
            conn.execute("""
                INSERT INTO members (telegram_id, full_name, birth_date, birth_day_month, role)
                VALUES (?, ?, '01.01.1990', '01-01', 'admin')
            """, (telegram_id, full_name))

        # Settings ga ham qo'shib qo'yish
        admin_setting = conn.execute("SELECT value FROM settings WHERE key = 'admin_ids'").fetchone()
        current_ids = set()
        if admin_setting and admin_setting["value"]:
            current_ids = {int(i.strip()) for i in admin_setting["value"].split(",") if i.strip().isdigit()}
        current_ids.add(telegram_id)
        val_str = ",".join(str(i) for i in current_ids)
        conn.execute("""
            INSERT INTO settings (key, value) VALUES ('admin_ids', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (val_str,))
        conn.commit()

# --- Oylik badallar bo'yicha funksiyalar ---

MONTH_NAMES_UZ = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
    5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
    9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
}

async def generate_monthly_dues(year: int, month: int, fee_amount: int = DEFAULT_MONTHLY_FEE) -> str:
    period_key = f"{year}-{month:02d}"
    month_name = MONTH_NAMES_UZ.get(month, f"{month}-oy")
    period_name = f"{year}-yil {month_name}"

    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO monthly_periods (period, name)
            VALUES (?, ?)
        """, (period_key, period_name))

        # Barcha faol xodimlarga oylik badal yozish
        members = conn.execute("SELECT id FROM members WHERE is_active = 1").fetchall()
        for m in members:
            conn.execute("""
                INSERT OR IGNORE INTO monthly_dues (period, member_id, amount, status)
                VALUES (?, ?, ?, 'unpaid')
            """, (period_key, m["id"], fee_amount))

        conn.commit()
    return period_name

async def mark_monthly_due_paid(due_id: int) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        due = conn.execute("""
            SELECT md.*, m.full_name, mp.name as period_name 
            FROM monthly_dues md
            JOIN members m ON md.member_id = m.id
            JOIN monthly_periods mp ON md.period = mp.period
            WHERE md.id = ?
        """, (due_id,)).fetchone()

        if not due or due["status"] == "paid":
            return False

        conn.execute("""
            UPDATE monthly_dues 
            SET status = 'paid', paid_at = ? 
            WHERE id = ?
        """, (now, due_id))

        desc = f"Oylik badal: {due['full_name']} ({due['period_name']})"
        conn.execute("""
            INSERT INTO transactions (type, category, amount, member_id, related_id, description, created_at)
            VALUES ('income', 'monthly_fee', ?, ?, ?, ?, ?)
        """, (due["amount"], due["member_id"], due_id, desc, now))

        conn.commit()
        return True

# --- Tug'ilgan kunlar bo'yicha funksiyalar ---

async def get_upcoming_birthdays(limit_days: int = 30) -> List[Dict[str, Any]]:
    today = date.today()
    members = await get_all_members(active_only=True)
    upcoming = []

    for m in members:
        day_str, month_str, *year_parts = m["birth_date"].split(".")
        b_day = int(day_str)
        b_month = int(month_str)

        try:
            this_year_bday = date(today.year, b_month, b_day)
        except ValueError:
            this_year_bday = date(today.year, b_month, 28)

        if this_year_bday < today:
            try:
                next_bday = date(today.year + 1, b_month, b_day)
            except ValueError:
                next_bday = date(today.year + 1, b_month, 28)
            days_left = (next_bday - today).days
            target_date = next_bday
        else:
            days_left = (this_year_bday - today).days
            target_date = this_year_bday

        if days_left <= limit_days:
            upcoming.append({
                "member": m,
                "days_left": days_left,
                "target_date": target_date.strftime("%d.%m.%Y"),
                "is_today": days_left == 0
            })

    upcoming.sort(key=lambda x: x["days_left"])
    return upcoming

async def trigger_birthday_event(member_id: int, year: int, gift_amount: int = DEFAULT_BIRTHDAY_GIFT, fee_per_member: int = DEFAULT_BIRTHDAY_FEE) -> Optional[int]:
    member = await get_member_by_id(member_id)
    if not member:
        return None

    event_date = f"{member['birth_date'][:5]}.{year}"

    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM birthday_events WHERE member_id = ? AND event_year = ?", (member_id, year)).fetchone()
        if existing:
            return existing["id"]

        cursor = conn.execute("""
            INSERT INTO birthday_events (member_id, event_year, event_date, gift_amount)
            VALUES (?, ?, ?, ?)
        """, (member_id, year, event_date, gift_amount))
        event_id = cursor.lastrowid

        # Qolgan barcha faol a'zolarga 25k badal yozish (tug'ilgan kun sohibidan tashqari!)
        all_members = conn.execute("SELECT id FROM members WHERE is_active = 1").fetchall()
        for m in all_members:
            if m["id"] != member_id:
                conn.execute("""
                    INSERT OR IGNORE INTO birthday_dues (event_id, payer_id, amount, status)
                    VALUES (?, ?, ?, 'unpaid')
                """, (event_id, m["id"], fee_per_member))

        conn.commit()
        return event_id

async def mark_birthday_due_paid(due_id: int) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        due = conn.execute("""
            SELECT bd.*, m.full_name as payer_name, bm.full_name as celebrant_name
            FROM birthday_dues bd
            JOIN members m ON bd.payer_id = m.id
            JOIN birthday_events be ON bd.event_id = be.id
            JOIN members bm ON be.member_id = bm.id
            WHERE bd.id = ?
        """, (due_id,)).fetchone()

        if not due or due["status"] == "paid":
            return False

        conn.execute("""
            UPDATE birthday_dues 
            SET status = 'paid', paid_at = ? 
            WHERE id = ?
        """, (now, due_id))

        desc = f"Tug'ilgan kun yig'imi: {due['payer_name']} ({due['celebrant_name']} uchun)"
        conn.execute("""
            INSERT INTO transactions (type, category, amount, member_id, related_id, description, created_at)
            VALUES ('income', 'birthday_fee', ?, ?, ?, ?, ?)
        """, (due["amount"], due["payer_id"], due_id, desc, now))

        conn.commit()
        return True

async def give_birthday_gift(event_id: int) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        event = conn.execute("""
            SELECT be.*, m.full_name
            FROM birthday_events be
            JOIN members m ON be.member_id = m.id
            WHERE be.id = ?
        """, (event_id,)).fetchone()

        if not event or event["gift_given"] == 1:
            return False

        conn.execute("""
            UPDATE birthday_events 
            SET gift_given = 1, gift_given_at = ? 
            WHERE id = ?
        """, (now, event_id))

        desc = f"Tug'ilgan kun mukofoti berildi: {event['full_name']} ga (500 000 so'm)"
        conn.execute("""
            INSERT INTO transactions (type, category, amount, member_id, related_id, description, created_at)
            VALUES ('expense', 'birthday_gift', ?, ?, ?, ?, ?)
        """, (event["gift_amount"], event["member_id"], event_id, desc, now))

        conn.commit()
        return True

# --- Chiqim va Qo'shimcha Kirimlar ---

async def add_custom_transaction(tx_type: str, category: str, amount: int, description: str, member_id: int = None) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO transactions (type, category, amount, member_id, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tx_type, category, amount, member_id, description, now))
        conn.commit()
        return cursor.lastrowid

# --- Kassa va Balans ---

async def get_fund_stats() -> Dict[str, Any]:
    with get_connection() as conn:
        total_income = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = 'income'").fetchone()["total"]
        total_expense = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = 'expense'").fetchone()["total"]
        monthly_income = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE category = 'monthly_fee'").fetchone()["total"]
        birthday_income = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE category = 'birthday_fee'").fetchone()["total"]
        gifts_expense = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE category = 'birthday_gift'").fetchone()["total"]
        other_expense = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE category = 'other_expense'").fetchone()["total"]

        balance = total_income - total_expense
        return {
            "balance": balance,
            "total_income": total_income,
            "total_expense": total_expense,
            "monthly_income": monthly_income,
            "birthday_income": birthday_income,
            "gifts_expense": gifts_expense,
            "other_expense": other_expense
        }

async def get_recent_transactions(limit: int = 10) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT t.*, m.full_name 
            FROM transactions t
            LEFT JOIN members m ON t.member_id = m.id
            ORDER BY t.id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]

# --- Qarzlar va Holat monitoringi ---

async def get_member_debts(member_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        monthly_debts = [dict(r) for r in conn.execute("""
            SELECT md.id, md.amount, mp.name as period_name
            FROM monthly_dues md
            JOIN monthly_periods mp ON md.period = mp.period
            WHERE md.member_id = ? AND md.status = 'unpaid'
            ORDER BY md.period ASC
        """, (member_id,)).fetchall()]

        birthday_debts = [dict(r) for r in conn.execute("""
            SELECT bd.id, bd.amount, m.full_name as celebrant_name, be.event_date
            FROM birthday_dues bd
            JOIN birthday_events be ON bd.event_id = be.id
            JOIN members m ON be.member_id = m.id
            WHERE bd.payer_id = ? AND bd.status = 'unpaid'
            ORDER BY be.id ASC
        """, (member_id,)).fetchall()]

        total_debt = sum(d["amount"] for d in monthly_debts) + sum(d["amount"] for d in birthday_debts)
        return {
            "monthly_debts": monthly_debts,
            "birthday_debts": birthday_debts,
            "total_debt": total_debt
        }

async def get_all_debtors() -> List[Dict[str, Any]]:
    members = await get_all_members(active_only=True)
    debtors = []
    for m in members:
        debts = await get_member_debts(m["id"])
        if debts["total_debt"] > 0:
            debtors.append({
                "member": m,
                "debts": debts
            })
    debtors.sort(key=lambda x: x["debts"]["total_debt"], reverse=True)
    return debtors

# --- Sozlamalar ---

async def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

async def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()
