"""
handlers/quiz.py

Квиз (Нативная Викторина Telegram c таймером и кнопкой остановки):
- Пользователь выбирает категорию → вариант → старт
- Каждый вопрос отправляется через функцию send_poll(type="quiz") с ограничением по времени
- Снизу доступна постоянная текстовая кнопка для досрочной остановки теста
- Результаты сохраняются как при полном прохождении, так и при досрочной остановке
"""

import json
import random
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, PollAnswer,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_questions, get_categories, save_result

router = Router()
log = logging.getLogger(__name__)

STOP_BTN = "🛑 Testni yakunlash"


# ─── FSM ─────────────────────────────────────────────────────────────────────

class QuizStates(StatesGroup):
    choosing_category = State()
    choosing_variant  = State()
    in_quiz           = State()


# ─── Keyboards ───────────────────────────────────────────────────────────────

def quiz_reply_kb() -> ReplyKeyboardMarkup:
    """Нижняя панель с кнопкой принудительной остановки теста"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=STOP_BTN)]],
        resize_keyboard=True
    )


# ─── Start quiz ──────────────────────────────────────────────────────────────

@router.message(F.text == "🧪 Testni boshlash")
async def cmd_start_quiz(message: Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("❗ Hali hech qanday savol yo'q. Avval savollar qo'shing.")
        return

    unique_cats = list(dict.fromkeys(row[0] for row in cats))
    builder = InlineKeyboardBuilder()
    for cat in unique_cats:
        builder.button(text=cat, callback_data=f"cat:{cat}")
    builder.adjust(2)

    await message.answer(
        "📚 *Kategoriyani tanlang:*",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuizStates.choosing_category)


@router.callback_query(QuizStates.choosing_category, F.data.startswith("cat:"))
async def chose_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)

    cats = await get_categories()
    variants = [row[1] for row in cats if row[0] == category]

    builder = InlineKeyboardBuilder()
    for v in variants:
        builder.button(text=f"Variant {v}", callback_data=f"var:{v}")
    builder.adjust(3)

    await callback.message.edit_text(
        f"📚 Kategoriya: *{category}*\n\n🔢 *Variantni tanlang:*",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuizStates.choosing_variant)


@router.callback_query(QuizStates.choosing_variant, F.data.startswith("var:"))
async def chose_variant(callback: CallbackQuery, state: FSMContext, bot: Bot):
    variant = callback.data.split(":", 1)[1]
    data = await state.get_data()
    category = data["category"]

    questions = await get_questions(category=category, variant=variant)
    if not questions:
        await callback.answer("❗ Bu variantda savollar topilmadi.", show_alert=True)
        return

    random.shuffle(questions)

    # Сохраняем базовые данные о пользователе и обнуляем счетчики
    await state.update_data(
        variant=variant,
        questions=questions,
        current=0,
        score=0,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        username=callback.from_user.username
    )
    await state.set_state(QuizStates.in_quiz)

    await callback.message.answer(
        f"✅ *{category} — Variant {variant}*\n"
        f"📊 Jami: *{len(questions)} ta savol*\n\n"
        f"Test boshlanmoqda... Har bir savolga *60 soniya* beriladi.",
        parse_mode="Markdown",
        reply_markup=quiz_reply_kb()
    )
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Запускаем первый вопрос по chat_id
    await send_question(callback.from_user.id, state, bot)


# ─── Send question ────────────────────────────────────────────────────────────

async def send_question(chat_id: int, state: FSMContext, bot: Bot):
    data = await state.get_data()
    questions = data["questions"]
    current   = data["current"]

    if current >= len(questions):
        await finish_quiz(chat_id, state, bot)
        return

    q       = questions[current]
    # Загружаем ответы безопасно
    answers = q["answers"] if isinstance(q["answers"], list) else json.loads(q["answers"])
    correct = int(q["correct"])
    num     = current + 1
    total   = len(questions)

    # Убираем лишние звездочки Markdown для красивого отображения
    question_text = str(q['question']).replace("*", "")
    options       = [str(ans).replace("*", "") for ans in answers]

    file_id  = q.get("file_id")
    file_id2 = q.get("file_id2")

    # 1. Отправляем фото, если они прикреплены к вопросу
    if file_id and file_id2:
        media = [InputMediaPhoto(media=file_id), InputMediaPhoto(media=file_id2)]
        await bot.send_media_group(chat_id, media)
    elif file_id:
        await bot.send_photo(chat_id, photo=file_id, reply_markup=quiz_reply_kb())

    # 2. Проверяем длину текста вопроса и ответов
    # Telegram лимиты: вопрос < 300 символов, каждый ответ < 100 символов
    is_question_long = len(question_text) > 300
    is_answers_long = any(len(opt) > 95 for opt in options)

    if is_question_long or is_answers_long:
        # Если что-то не влезает, собираем отдельное текстовое сообщение
        text_parts = [f"❓ *Savol {num}/{total}*\n\n{q['question']}"]
        
        # Если ответы слишком длинные, пишем их в тексте сообщения
        if is_answers_long:
            letters = ["A", "B", "C", "D", "E", "F"]
            text_parts.append("\n*Variantlar:*")
            for i, opt in enumerate(options):
                # Формируем список A) текст, B) текст...
                text_parts.append(f"*{letters[i]})* {opt}")
            
            # А в саму викторину пойдут просто буквы A, B, C, D
            options = letters[:len(options)]
        
        # Отправляем длинный текст обычным сообщением
        await bot.send_message(
            chat_id, 
            "\n".join(text_parts), 
            parse_mode="Markdown", 
            reply_markup=quiz_reply_kb()
        )
        poll_question = f"Javobingizni tanlang (Savol {num}/{total}):"
    else:
        poll_question = f"({num}/{total}) {question_text}"

    # 3. Отправка нативной викторины с таймером
    try:
        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=poll_question,
            options=options,
            type="quiz",
            correct_option_id=correct,
            is_anonymous=False,      # Обязательно False
            open_period=60,          # ⏱ ТАЙМЕР: 60 секунд
            reply_markup=quiz_reply_kb()
        )
        # Запоминаем ID текущего опроса
        await state.update_data(last_poll_id=poll_msg.poll.id)
    except Exception as e:
        log.exception("Викторина не отправилась")
        await bot.send_message(
            chat_id, 
            "⚠️ Kutilmagan xatolik yuz berdi. Keyingi savolga o'tilmoqda..."
        )
        await state.update_data(current=current + 1)
        await send_question(chat_id, state, bot)

# ─── Poll Answer Handler (Авто-переключение при клике) ────────────────────────

@router.poll_answer()
async def handle_quiz_answer(poll_answer: PollAnswer, state: FSMContext, bot: Bot):
    """Срабатывает автоматически, когда пользователь нажимает на вариант ответа"""
    current_state = await state.get_state()
    if current_state != QuizStates.in_quiz.state:
        return

    data = await state.get_data()
    if not data or data.get("last_poll_id") != poll_answer.poll_id:
        return

    questions = data["questions"]
    current   = data["current"]
    score     = data["score"]

    q = questions[current]
    correct = int(q["correct"])
    chosen = poll_answer.option_ids[0]

    # Считаем очки
    if chosen == correct:
        score += 1

    # Переключаем индекс на следующий вопрос
    await state.update_data(current=current + 1, score=score)
    
    # chat_id берём из state данных — работает и в личке и в группе
    chat_id = data.get("chat_id") or poll_answer.user.id
    await send_question(chat_id, state, bot)


# ─── Принудительная остановка теста ──────────────────────────────────────────

@router.message(QuizStates.in_quiz, F.text == STOP_BTN)
async def cmd_stop_quiz(message: Message, state: FSMContext):
    """Срабатывает при нажатии на кнопку '🛑 Testni yakunlash'"""
    data = await state.get_data()
    if not data:
        await state.clear()
        return

    score    = data.get("score", 0)
    current  = data.get("current", 0)
    category = data.get("category", "—")
    variant  = data.get("variant",  "—")
    user_id  = data.get("user_id")
    username = data.get("username")

    # Сохраняем промежуточный результат (сколько успел пройти)
    await save_result(
        user_id  = user_id,
        username = username,
        score    = score,
        total    = current,  # Считаем "всего вопросов" как количество отвеченных до стопа
        category = category,
        variant  = variant
    )

    from handlers.start import main_kb
    await message.answer(
        f"🛑 *Test majburiy to'xtatildi.*\n\n"
        f"📚 Kategoriya: *{category}* — Variant *{variant}*\n"
        f"📊 Siz bajargan qism: *{score}/{current}*",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )
    await state.clear()


# ─── Finish ──────────────────────────────────────────────────────────────────

async def finish_quiz(chat_id: int, state: FSMContext, bot: Bot):
    """Вызывается при успешном прохождении всех вопросов"""
    data     = await state.get_data()
    score    = data["score"]
    total    = len(data["questions"])
    category = data.get("category", "—")
    variant  = data.get("variant",  "—")
    user_id  = data.get("user_id")
    username = data.get("username")

    pct = round(score / total * 100) if total else 0

    if pct >= 90:
        emoji = "🏆"
    elif pct >= 70:
        emoji = "👍"
    elif pct >= 50:
        emoji = "😐"
    else:
        emoji = "📚"

    await save_result(
        user_id  = user_id,
        username = username,
        score    = score,
        total    = total,
        category = category,
        variant  = variant
    )

    from handlers.start import main_kb
    await bot.send_message(
        chat_id,
        f"{emoji} *Test yakunlandi!*\n\n"
        f"📚 Kategoriya: *{category}* — Variant *{variant}*\n"
        f"✅ To'g'ri javoblar: *{score}/{total}* ({pct}%)",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )
    await state.clear()