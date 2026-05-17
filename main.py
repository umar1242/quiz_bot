import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.db import init_db
from handlers import start, quiz, stats

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(quiz.router)
    dp.include_router(stats.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())