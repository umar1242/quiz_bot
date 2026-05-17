from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_user_stats, get_leaderboard
import aiosqlite

DB_PATH = "database/quiz.db"
router = Router()

@router.callback_query(F.data == "menu_stats")
async def show_stats(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id)
    leaderboard = await get_leaderboard()

    count = stats[0] or 0
    avg = stats[1] or 0
    best = stats[2] or 0

    text = (
        f"📊 Моя статистика:\n\n"
        f"🎯 Тестов пройдено: {count}\n"
        f"📈 Средний балл: {avg}%\n"
        f"🏆 Лучший результат: {round(best)}%\n\n"
    )

    if leaderboard:
        text += "🏅 Топ игроков:\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (name, attempts, avg_score) in enumerate(leaderboard):
            text += f"{medals[i]} {name}\n"
            text += f"   📝 Тестов: {attempts} | 📈 Средний: {avg_score}%\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои последние результаты", callback_data="my_results")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_start")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "my_results")
async def show_my_results(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT category, variant, score, total, time_spent, wrong_questions, finished_at
            FROM results
            WHERE telegram_id = ?
            ORDER BY finished_at DESC
            LIMIT 5
        """, (callback.from_user.id,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await callback.answer("У тебя пока нет результатов!", show_alert=True)
        return

    text = "📋 Мои последние 5 результатов:\n\n"
    for i, (cat, var, score, total, time_spent, wrong, date) in enumerate(rows, 1):
        percent = round(score * 100 / total)
        mins = time_spent // 60
        secs = time_spent % 60
        date_short = date[:10] if date else ""

        text += (
            f"{i}. 📂 {cat} | Вариант {var}\n"
            f"   ✅ {score}/{total} | 📊 {percent}% | ⏱ {mins:02d}:{secs:02d} | 📅 {date_short}\n"
        )
        if wrong:
            text += f"   ❌ Ошибки: {wrong}\n"
        text += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_stats")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()