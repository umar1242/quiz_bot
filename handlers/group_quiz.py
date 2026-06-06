"""
handlers/group_quiz.py

Групповой тест в Telegram-группе.

Флоу:
1. Владелец в личке получает карточку с кнопкой «👥 Guruhda boshlash»
2. Бот добавляется в группу, владелец пишет /startquiz_Kategoriya_Variant
3. 10 сек отсчёт → вопросы идут один за другим
4. На каждый вопрос: обычный poll (не quiz) + таймер 60 сек
5. Переход к следующему: либо все участники ответили, либо таймер истёк
6. После каждого вопроса — кто ответил правильно/неправильно
7. В конце — рейтинг 🥇🥈🥉

Команды в группе:
  /startquiz_Kategoriya_Variant  — запустить (только владелец)
  /stopquiz                      — остановить досрочно (только владелец)
"""

import asyncio
import json
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, PollAnswer,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram import html

from database.db import (
    get_questions,
    get_active_group_session,
    create_group_session,
    update_group_session_idx,
    close_group_session,
    save_group_answer,
    get_group_answers,
    get_group_scoreboard,
)

router = Router()
log = logging.getLogger(__name__)

LETTERS = ["A", "B", "C", "D"]

# in-memory: session_id → asyncio.Task (таймер вопроса)
_timers: dict[int, asyncio.Task] = {}

# in-memory: poll_id → session_id  (чтобы найти сессию по poll_answer)
_poll_to_session: dict[str, int] = {}

# in-memory: session_id → question_idx который сейчас активен
_session_poll_idx: dict[int, int] = {}


# ─── Deep-link карточка (вызывается из upload.py) ────────────────────────────

async def send_group_launch_card(message: Message, bot: Bot,
                                  category: str, variant: str,
                                  total: int, bot_username: str):
    safe_cat = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF\u0041-\u007A]', '_', category)
    safe_var = re.sub(r'[^a-zA-Z0-9]', '_', variant)
    command  = f"/startquiz_{safe_cat}_{safe_var}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="▶️ Boshlash",
                url=f"https://t.me/{bot_username}?start=quiz_{safe_cat}_{safe_var}"
            ),
            InlineKeyboardButton(
                text="📤 Ulashish",
                switch_inline_query=f"quiz {category} {variant}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="👥 Guruhda boshlash",
                url=f"https://t.me/{bot_username}?startgroup=quiz_{safe_cat}_{safe_var}"
            ),
        ],
    ])

    await message.answer(
        f"📋 <b>{html.quote(category)} — Variant {html.quote(variant)}</b>\n"
        f"📊 Savollar: <b>{total} ta</b>\n\n"
        f"👥 <b>Guruhda ishlatish uchun:</b>\n"
        f"Botni guruhga qo'shing va yuboring:\n"
        f"<code>{command}</code>",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ─── /startquiz_Kategoriya_Variant ───────────────────────────────────────────

@router.message(Command(re.compile(r"startquiz_.+")))
async def cmd_startquiz(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Bu buyruq faqat guruhlarda ishlaydi.")
        return

    text = message.text or ""
    # Поддержка формата /startquiz_Cat_Var и /startquiz_Cat_Var@botname
    m = re.match(r"/startquiz_(.+?)_([^_\s@]+)(?:@\S+)?(?:\s|$)", text)
    if not m:
        await message.answer(
            "❗ Format: <code>/startquiz_Kategoriya_Variant</code>",
            parse_mode="HTML"
        )
        return

    category = m.group(1).replace("_", " ")
    variant  = m.group(2)
    owner_id = message.from_user.id

    # Проверяем нет ли активной сессии
    existing = await get_active_group_session(message.chat.id)
    if existing:
        await message.answer(
            "❗ Guruhda allaqachon faol test bor.\n"
            "Avval uni to'xtating: <code>/stopquiz</code>",
            parse_mode="HTML"
        )
        return

    questions = await get_questions(category=category, variant=variant)
    if not questions:
        await message.answer(
            f"❗ <b>{html.quote(category)} — Variant {html.quote(variant)}</b> "
            f"uchun savollar topilmadi.",
            parse_mode="HTML"
        )
        return

    q_ids = [q["id"] for q in questions]
    session_id = await create_group_session(
        chat_id       = message.chat.id,
        owner_id      = owner_id,
        category      = category,
        variant       = variant,
        question_ids  = q_ids,
        timer_seconds = 60,
    )

    # Получаем количество участников группы
    try:
        chat = await bot.get_chat(message.chat.id)
        member_count = await bot.get_chat_member_count(message.chat.id)
        # Вычитаем ботов (обычно 1)
        participant_count = max(member_count - 1, 1)
    except Exception:
        participant_count = 999  # если не удалось — ждём таймер

    await message.answer(
        f"🎯 <b>{html.quote(category)} — Variant {html.quote(variant)}</b>\n"
        f"📊 Jami: <b>{len(questions)} ta savol</b>\n"
        f"👥 Ishtirokchilar: <b>{participant_count} kishi</b>\n"
        f"⏱ Har bir savolga: <b>60 soniya</b>\n\n"
        f"⏳ Test <b>10 soniyadan</b> keyin boshlanadi!",
        parse_mode="HTML"
    )

    await asyncio.sleep(10)
    await _send_question(bot, message.chat.id, session_id, questions,
                          idx=0, participant_count=participant_count)


# ─── /stopquiz ───────────────────────────────────────────────────────────────

@router.message(Command("stopquiz"))
async def cmd_stopquiz(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        return

    session = await get_active_group_session(message.chat.id)
    if not session:
        await message.answer("Hozir faol test yo'q.")
        return

    if message.from_user.id != session["owner_id"]:
        await message.answer("❗ Testni faqat uni boshlagan kishi to'xtata oladi.")
        return

    _cancel_timer(session["id"])
    await close_group_session(session["id"])
    await message.answer("🛑 Test to'xtatildi.")
    await _send_scoreboard(bot, message.chat.id, session["id"],
                           session["category"], session["variant"],
                           len(session["questions"]))


# ─── Poll answer handler ──────────────────────────────────────────────────────

@router.poll_answer()
async def group_poll_answer(poll_answer: PollAnswer, bot: Bot):
    poll_id    = poll_answer.poll_id
    session_id = _poll_to_session.get(poll_id)
    if session_id is None:
        return  # не наш poll

    q_idx = _session_poll_idx.get(session_id)
    if q_idx is None:
        return

    # Находим сессию через БД чтобы получить chat_id
    # (храним chat_id в _session_chat тоже)
    chat_id = _session_chat.get(session_id)
    if not chat_id:
        return

    session = await get_active_group_session(chat_id)
    if not session or session["id"] != session_id:
        return

    questions = await get_questions(
        category=session["category"], variant=session["variant"]
    )
    q_id = session["questions"][q_idx]
    q    = next((x for x in questions if x["id"] == q_id), None)
    if not q:
        return

    correct    = int(q["correct"])
    chosen     = poll_answer.option_ids[0]
    is_correct = 1 if chosen == correct else 0

    await save_group_answer(
        session_id   = session_id,
        question_idx = q_idx,
        user_id      = poll_answer.user.id,
        username     = poll_answer.user.username,
        first_name   = poll_answer.user.first_name or "Foydalanuvchi",
        chosen       = chosen,
        is_correct   = is_correct,
    )

    # Проверяем — все ли ответили
    participant_count = _session_participants.get(session_id, 999)
    answers = await get_group_answers(session_id, q_idx)

    if len(answers) >= participant_count:
        # Все ответили — отменяем таймер и переходим досрочно
        _cancel_timer(session_id)
        await _advance_question(bot, chat_id, session_id, questions, q_idx)


# ─── Отправка вопроса ─────────────────────────────────────────────────────────

# Дополнительные in-memory словари
_session_chat:         dict[int, int] = {}   # session_id → chat_id
_session_participants: dict[int, int] = {}   # session_id → ожидаемое кол-во участников


async def _send_question(bot: Bot, chat_id: int, session_id: int,
                          questions: list, idx: int, participant_count: int):
    session = await get_active_group_session(chat_id)
    if not session or not session["is_active"]:
        return

    total = len(session["questions"])

    if idx >= total:
        await _finish(bot, chat_id, session)
        return

    await update_group_session_idx(session_id, idx)

    # Сохраняем в память
    _session_chat[session_id]         = chat_id
    _session_participants[session_id] = participant_count
    _session_poll_idx[session_id]     = idx

    q_id = session["questions"][idx]
    q    = next((x for x in questions if x["id"] == q_id), None)
    if not q:
        return

    answers  = q["answers"] if isinstance(q["answers"], list) else json.loads(q["answers"])
    question = str(q["question"]).replace("*", "")
    options  = [str(a).replace("*", "") for a in answers]

    # Telegram лимит: вопрос ≤ 300 символов, вариант ≤ 100 символов
    is_long_q = len(question) > 290
    is_long_a = any(len(o) > 90 for o in options)

    # Фото
    file_id  = q.get("file_id")
    file_id2 = q.get("file_id2")
    if file_id and file_id2:
        from aiogram.types import InputMediaPhoto
        await bot.send_media_group(chat_id, [
            InputMediaPhoto(media=file_id),
            InputMediaPhoto(media=file_id2),
        ])
    elif file_id:
        await bot.send_photo(chat_id, photo=file_id)

    # Если текст длинный — отправляем отдельным сообщением
    if is_long_q or is_long_a:
        letters = ["A", "B", "C", "D"]
        lines   = [f"❓ <b>Savol {idx+1}/{total}</b>\n\n{html.quote(q['question'])}"]
        if is_long_a:
            lines.append("")
            for i, opt in enumerate(options):
                lines.append(f"<b>{letters[i]})</b> {html.quote(opt)}")
            options = letters[:len(options)]
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        poll_q = f"Javobingizni tanlang ({idx+1}/{total}):"
    else:
        poll_q = f"({idx+1}/{total}) {question}"

    # Отправляем обычный poll (не quiz!) — чтобы получать poll_answer
    poll_msg = await bot.send_poll(
        chat_id   = chat_id,
        question  = poll_q,
        options   = options,
        type      = "regular",        # regular, не quiz
        is_anonymous = False,
        open_period  = session["timer_seconds"],
    )

    # Запоминаем poll_id → session_id
    _poll_to_session[poll_msg.poll.id] = session_id

    # Запускаем таймер
    task = asyncio.create_task(
        _timer_task(bot, chat_id, session_id, questions, idx,
                    session["timer_seconds"])
    )
    _timers[session_id] = task


async def _timer_task(bot: Bot, chat_id: int, session_id: int,
                       questions: list, idx: int, seconds: int):
    """Ждём seconds секунд, потом переходим к следующему вопросу."""
    await asyncio.sleep(seconds)

    session = await get_active_group_session(chat_id)
    if not session or session["id"] != session_id or not session["is_active"]:
        return
    if session["current_idx"] != idx:
        return  # уже перешли досрочно

    await _advance_question(bot, chat_id, session_id, questions, idx)


async def _advance_question(bot: Bot, chat_id: int, session_id: int,
                              questions: list, idx: int):
    """Показать результат текущего вопроса и перейти к следующему."""
    session = await get_active_group_session(chat_id)
    if not session or not session["is_active"]:
        return

    await _send_question_result(bot, chat_id, session_id, questions, idx)
    await asyncio.sleep(3)
    await _send_question(bot, chat_id, session_id, questions,
                          idx + 1,
                          _session_participants.get(session_id, 999))


# ─── Результат вопроса ────────────────────────────────────────────────────────

async def _send_question_result(bot: Bot, chat_id: int, session_id: int,
                                  questions: list, idx: int):
    session = await get_active_group_session(chat_id)
    if not session:
        return

    q_id = session["questions"][idx]
    q    = next((x for x in questions if x["id"] == q_id), None)
    if not q:
        return

    answers  = q["answers"] if isinstance(q["answers"], list) else json.loads(q["answers"])
    correct  = int(q["correct"])
    ans_rows = await get_group_answers(session_id, idx)

    correct_users = [r for r in ans_rows if r["is_correct"]]
    wrong_users   = [r for r in ans_rows if not r["is_correct"]]

    lines = [
        f"📊 <b>Savol {idx+1} natijalari</b>",
        f"✅ To'g'ri javob: <b>{LETTERS[correct]}) {html.quote(answers[correct])}</b>\n",
    ]

    if correct_users:
        names = ", ".join(
            html.quote(r["first_name"] or r["username"] or "?")
            for r in correct_users[:10]
        )
        lines.append(f"🏆 To'g'ri ({len(correct_users)}): {names}")
    else:
        lines.append("😔 Hech kim to'g'ri javob bermadi")

    if wrong_users:
        w_names = ", ".join(
            html.quote(r["first_name"] or r["username"] or "?")
            for r in wrong_users[:10]
        )
        lines.append(f"❌ Noto'g'ri ({len(wrong_users)}): {w_names}")

    if not ans_rows:
        lines.append("⚠️ Hech kim javob bermadi")

    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


# ─── Финиш ───────────────────────────────────────────────────────────────────

async def _finish(bot: Bot, chat_id: int, session: dict):
    _cancel_timer(session["id"])
    await close_group_session(session["id"])
    # Чистим память
    _session_chat.pop(session["id"], None)
    _session_participants.pop(session["id"], None)
    _session_poll_idx.pop(session["id"], None)

    await _send_scoreboard(bot, chat_id, session["id"],
                           session["category"], session["variant"],
                           len(session["questions"]))


async def _send_scoreboard(bot: Bot, chat_id: int, session_id: int,
                            category: str, variant: str, total: int):
    rows   = await get_group_scoreboard(session_id)
    medals = ["🥇", "🥈", "🥉"]

    lines = [
        f"🏆 <b>Test yakunlandi!</b>",
        f"📚 {html.quote(category)} — Variant {html.quote(variant)}\n",
        "<b>Reyting:</b>",
    ]

    if not rows:
        lines.append("Hech kim qatnashmadi.")
    else:
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"{i+1}."
            name  = html.quote(row["first_name"] or row["username"] or "?")
            pct   = round(row["correct"] / total * 100) if total else 0
            lines.append(f"{medal} {name} — {row['correct']}/{total} ({pct}%)")

    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


# ─── Хелпер ──────────────────────────────────────────────────────────────────

def _cancel_timer(session_id: int):
    task = _timers.pop(session_id, None)
    if task and not task.done():
        task.cancel()
