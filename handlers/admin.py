from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
import aiosqlite

router = Router()

ADMIN_ID = 1043620738  # твой Telegram ID
DB_PATH = "database/quiz.db"

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У тебя нет доступа!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Общая статистика
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM results") as cursor:
            total_tests = (await cursor.fetchone())[0]

        # Все пользователи с деталями
        async with db.execute("""
            SELECT u.name, u.telegram_id,
                   COUNT(r.id) as tests,
                   ROUND(AVG(r.score * 100.0 / r.total), 1) as avg_score,
                   MAX(r.score * 100.0 / r.total) as best
            FROM users u
            LEFT JOIN results r ON u.telegram_id = r.telegram_id
            GROUP BY u.telegram_id
            ORDER BY avg_score DESC
        """) as cursor:
            users = await cursor.fetchall()

    text = (
        f"👑 Админ панель\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📝 Всего тестов пройдено: {total_tests}\n\n"
        f"📊 Статистика пользователей:\n\n"
    )

    for name, tg_id, tests, avg, best in users:
        avg = avg or 0
        best = best or 0
        text += (
            f"👤 {name}\n"
            f"   🆔 {tg_id}\n"
            f"   📝 Тестов: {tests}\n"
            f"   📈 Средний: {avg}%\n"
            f"   🏆 Лучший: {round(best)}%\n\n"
        )

    await message.answer(text)