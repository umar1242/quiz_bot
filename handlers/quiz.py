import asyncio
import time
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import save_result
import json

router = Router()

QUIZ_DURATION = 30 * 60

def load_questions():
    with open("data/questions.json", encoding="utf-8") as f:
        return json.load(f)

class QuizState(StatesGroup):
    choosing_category = State()
    choosing_variant = State()
    answering = State()

@router.callback_query(F.data == "menu_quiz")
async def show_categories(callback: CallbackQuery, state: FSMContext):
    questions = load_questions()
    categories = sorted(set(q["category"] for q in questions))
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")]
               for cat in categories]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_start")])
    await callback.message.edit_text(
        "📚 Выбери категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(QuizState.choosing_category)
    await callback.answer()

@router.callback_query(QuizState.choosing_category, F.data.startswith("cat:"))
async def show_variants(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    questions = load_questions()
    variants = sorted(set(q["variant"] for q in questions if q["category"] == category))
    buttons = [[InlineKeyboardButton(text=f"Вариант {v}", callback_data=f"var:{category}:{v}")]
               for v in variants]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_quiz")])
    await callback.message.edit_text(
        f"📂 Категория: {category}\n\nВыбери вариант:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(QuizState.choosing_variant)
    await callback.answer()

@router.callback_query(QuizState.choosing_variant, F.data.startswith("var:"))
async def start_quiz(callback: CallbackQuery, state: FSMContext):
    _, category, variant = callback.data.split(":", 2)
    questions = load_questions()
    qs = [q for q in questions if q["category"] == category and q["variant"] == variant]
    await state.update_data(
        questions=qs, index=0, score=0, wrong=[],
        category=category, variant=variant,
        start_time=time.time(), chat_id=callback.message.chat.id
    )
    await callback.message.edit_text(
        f"🚀 Начинаем!\n\n"
        f"📂 {category} | Вариант {variant}\n"
        f"❓ Вопросов: {len(qs)}\n"
        f"⏱ Время: 30 минут\n\nУдачи! 💪"
    )
    await state.set_state(QuizState.answering)
    await send_question(callback.message, state)
    await callback.answer()
    asyncio.create_task(quiz_timer(callback.message, state))

async def send_question(message: Message, state: FSMContext):
    data = await state.get_data()
    index = data["index"]
    questions = data["questions"]

    if index >= len(questions):
        await finish_quiz(message, state)
        return

    q = questions[index]
    elapsed = int(time.time() - data["start_time"])
    remaining = max(0, QUIZ_DURATION - elapsed)
    mins = remaining // 60
    secs = remaining % 60
    caption = f"❓ Вопрос {index + 1}/{len(questions)}  |  ⏱ {mins:02d}:{secs:02d}"

    buttons = [[
        InlineKeyboardButton(text="A", callback_data="ans:0"),
        InlineKeyboardButton(text="B", callback_data="ans:1"),
        InlineKeyboardButton(text="C", callback_data="ans:2"),
        InlineKeyboardButton(text="D", callback_data="ans:3"),
    ]]

    if "file_id2" in q:
        await message.answer_photo(photo=q["file_id"])
        await message.answer_photo(
            photo=q["file_id2"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await message.answer_photo(
            photo=q["file_id"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

@router.callback_query(QuizState.answering, F.data.startswith("ans:"))
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    chosen = int(callback.data.split(":")[1])
    data = await state.get_data()

    elapsed = time.time() - data["start_time"]
    if elapsed > QUIZ_DURATION:
        await callback.answer("⏰ Время вышло!")
        return

    index = data["index"]
    questions = data["questions"]
    q = questions[index]
    correct = q["correct"]
    wrong = data["wrong"]

    if chosen == correct:
        score = data["score"] + 1
        await callback.answer("✅ Правильно!")
    else:
        score = data["score"]
        wrong = wrong + [index + 1]
        await callback.answer(f"❌ Неверно! Правильный: {'ABCD'[correct]}")

    await state.update_data(score=score, index=index + 1, wrong=wrong)
    await send_question(callback.message, state)

async def quiz_timer(message: Message, state: FSMContext):
    await asyncio.sleep(QUIZ_DURATION)
    current = await state.get_state()
    if current == QuizState.answering:
        await message.answer("⏰ Время вышло! Тест завершён.")
        await finish_quiz(message, state)

async def finish_quiz(message: Message, state: FSMContext):
    data = await state.get_data()
    score = data["score"]
    total = len(data["questions"])
    elapsed = int(time.time() - data["start_time"])
    mins = elapsed // 60
    secs = elapsed % 60
    percent = round(score * 100 / total)
    wrong = data["wrong"]

    await save_result(
        telegram_id=message.chat.id,
        category=data["category"],
        variant=data["variant"],
        score=score, total=total,
        time_spent=elapsed,
        wrong_questions=wrong
    )

    text = (
        f"🏁 Тест завершён!\n\n"
        f"📂 {data['category']} | Вариант {data['variant']}\n"
        f"✅ Правильных: {score} из {total}\n"
        f"❌ Неправильных: {total - score} из {total}\n"
        f"📊 Результат: {percent}%\n"
        f"⏱ Время: {mins:02d}:{secs:02d}\n"
    )
    if wrong:
        text += f"\n❌ Неверные вопросы №:\n"
        text += ", ".join(f"#{n}" for n in wrong)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data=f"var:{data['category']}:{data['variant']}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_start")]
    ])
    await message.answer(text, reply_markup=keyboard)
    await state.clear()

@router.callback_query(F.data == "back_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    from handlers.start import cmd_start
    await state.clear()
    await cmd_start(callback.message)
    await callback.answer()