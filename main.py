import asyncio
import logging
import re

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN
from database.db import init_db, get_questions
from handlers import start, quiz, stats, upload
from handlers import group_quiz

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher()

    # ── Deep link handler: /start quiz_Category_Variant ──────────────────────
    @dp.message(CommandStart(deep_link=True))
    async def deep_link_start(message: Message, state: FSMContext):
        payload = message.text.split(maxsplit=1)[1] if " " in message.text else ""
        m = re.match(r"quiz_(.+?)_([^_\s]+)$", payload)
        if m:
            category  = m.group(1).replace("_", " ")
            variant   = m.group(2)
            questions = await get_questions(category=category, variant=variant)
            if questions:
                from handlers.quiz import QuizStates, send_question, quiz_reply_kb
                await state.update_data(
                    category  = category,
                    variant   = variant,
                    questions = questions,
                    current   = 0,
                    score     = 0,
                    chat_id   = message.chat.id,
                    user_id   = message.from_user.id,
                    username  = message.from_user.username,
                )
                await state.set_state(QuizStates.in_quiz)
                await message.answer(
                    f"<b>{category} — Variant {variant}</b>\n"
                    f"Jami: <b>{len(questions)} ta savol</b>\n\n"
                    "Test boshlanmoqda... Har bir savolga <b>60 soniya</b> beriladi.",
                    parse_mode="HTML",
                    reply_markup=quiz_reply_kb()
                )
                await send_question(message.chat.id, state, bot)
                return
        # fallback — normal /start
        from handlers.start import cmd_start
        await cmd_start(message, state)

    # ── Routers ──────────────────────────────────────────────────────────────
    dp.include_router(start.router)
    dp.include_router(upload.router)
    dp.include_router(quiz.router)
    dp.include_router(stats.router)
    dp.include_router(group_quiz.router)

    await dp.start_polling(bot, allowed_updates=["message", "poll_answer", "callback_query", "poll"])


if __name__ == "__main__":
    asyncio.run(main())