from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db import register_user

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await register_user(message.from_user.id, message.from_user.full_name)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Начать тест", callback_data="menu_quiz")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="menu_stats")]
    ])

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🧬 Добро пожаловать в Quiz-бот по биологии!\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )