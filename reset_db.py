import asyncio
import os
from database.db import init_db, DB_PATH

async def reset():
    if DB_PATH.exists():
        try:
            os.remove(DB_PATH)
            print("Eski baza o'chirildi.")
        except Exception as e:
            print(f"Baza o'chirishda xatolik: {e}")
    await init_db()
    print("Yangi toza ma'lumotlar bazasi tayyor!")

if __name__ == "__main__":
    asyncio.run(reset())
