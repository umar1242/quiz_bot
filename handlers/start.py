"""
handlers/start.py
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Testni boshlash")],
            [KeyboardButton(text="➕ Savol qo'shish")],
            [KeyboardButton(text="📊 Mening natijalarim")],
            [KeyboardButton(text="ℹ️ Yordam")],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Salom, *{message.from_user.first_name}*!\n\n"
        "Bu — test o'tkazish boti.\n\n"
        "📌 Nima qilishingiz mumkin:\n"
        "• *Testni boshlash* — mavjud savollardan test yechish\n"
        "• *Savol qo'shish* — yangi savollar yuklash\n"
        "• *Mening natijalarim* — o'tgan testlar tarixi",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


@router.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: Message):
    await message.answer(
        "📖 *Savol yuklash — ikki xil format*\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *FORMAT 1 — Klassik*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "`+` belgisi — savollar o'rtasidagi chegara\n"
        "`=` belgisi — javoblar o'rtasidagi chegara\n"
        "`#` belgisi — to'g'ri javob oldida (faqat bitta)\n"
        "Belgilar soni muhim emas: `+`, `++`, `+++` — barchasi qabul qilinadi.\n\n"
        "```\n"
        "+\n"
        "Yorug'likning tezligi qancha?\n"
        "=\n"
        "#3×10⁸ m/s\n"
        "=\n"
        "3×10⁶ m/s\n"
        "=\n"
        "3×10⁴ m/s\n"
        "=\n"
        "3×10² m/s\n"
        "+\n"
        "```\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *FORMAT 2 — Oddiy*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "`*` belgisi — to'g'ri javob oldida (faqat bitta)\n"
        "Bo'sh qator — savollar orasidagi chegara\n\n"
        "```\n"
        "Yorug'likning tezligi qancha?\n"
        "*3×10⁸ m/s\n"
        "3×10⁶ m/s\n"
        "3×10⁴ m/s\n"
        "3×10² m/s\n"
        "\n"
        "Nyutonning 2-qonuni?\n"
        "F = m/a\n"
        "*F = ma\n"
        "F = a/m\n"
        "F = m²a\n"
        "```\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📎 *Qabul qilinadigan fayl turlari:*\n"
        "`.txt`  `.docx`  `.pdf`\n\n"

        "📸 *Rasmli savollar uchun:*\n"
        "Avval rasmlarni yuboring, so'ng faylni yuboring.\n"
        "Rasmlar savollar tartibiga ko'ra biriktiriladi.\n\n"

        "❓ Muammo bo'lsa — https://t.me/Umar0500 ga yozing.",
        parse_mode="Markdown",
    )