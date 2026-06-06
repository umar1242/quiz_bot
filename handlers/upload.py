"""
handlers/upload.py

Поток добавления вопросов:
1. Пользователь нажимает «➕ Savol qo'shish»
2. Бот спрашивает категорию
3. Бот спрашивает вариант
4. Бот спрашивает ФОРМАТ файла (Классик или Оддий)
5. Пользователь отправляет фото (опционально)
6. Пользователь отправляет .txt / .docx / .pdf файл
7. Бот парсит, связывает фото и сохраняет в БД

═══════════════════════════════════════════════════
ФОРМАТ 1 — «Классик» (разделители + и =)
═══════════════════════════════════════════════════
Принимается любое количество знаков (1 и более):
  +  или  ++  или  +++  — разделитель вопросов
  =  или  ==  или  ===  — разделитель ответов
  #  — строго один символ перед правильным ответом

Пример:
  +
  Savol matni?
  =
  #To'g'ri javob
  =
  Javob 2
  =
  Javob 3
  =
  Javob 4
  +

═══════════════════════════════════════════════════
ФОРМАТ 2 — «Оддий» (пустая строка = новый вопрос)
═══════════════════════════════════════════════════
Каждый вопрос — block строк без пустых строк внутри.
Блоки разделяются одной или несколькими пустыми строками.
Правильный ответ отмечается * в начале строки.

Пример:
  Savol matni?
  Javob 1
  *To'g'ri javob
  Javob 3
  Javob 4

  Savol 2?
  *To'g'ri javob
  Javob 2
  Javob 3
  Javob 4
"""

import io
import re
import logging

from aiogram import Router, F, Bot, html
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import add_question

router = Router()
log = logging.getLogger(__name__)

CANCEL_BTN = "❌ Bekor qilish"
SKIP_BTN   = "⏭ Fotosiz davom etish"

SUPPORTED_EXTENSIONS = (".txt", ".docx", ".pdf")


# ─── Keyboards ───────────────────────────────────────────────────────────────

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_BTN)]],
        resize_keyboard=True
    )


def skip_or_cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SKIP_BTN)],
            [KeyboardButton(text=CANCEL_BTN)],
        ],
        resize_keyboard=True
    )


def format_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Klassik (+ va =)",    callback_data="fmt:classic"),
            InlineKeyboardButton(text="📝 Oddiy (bo'sh qator)", callback_data="fmt:simple"),
        ]
    ])


# ─── FSM ─────────────────────────────────────────────────────────────────────

class UploadStates(StatesGroup):
    waiting_category = State()
    waiting_variant  = State()
    choosing_format  = State()
    waiting_photos   = State()
    waiting_file     = State()


# ─── Entry / Cancel ──────────────────────────────────────────────────────────

@router.message(F.text == "➕ Savol qo'shish")
async def cmd_add_questions(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📚 <b>Kategoriya nomini kiriting</b>\n<i>(masalan: Fizika, Biologiya, Kimyo)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(UploadStates.waiting_category)


@router.message(F.text == CANCEL_BTN)
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    from handlers.start import main_kb
    await message.answer("❌ Bekor qilindi.", reply_markup=main_kb())


# ─── Step 1: Category ────────────────────────────────────────────────────────

@router.message(UploadStates.waiting_category)
async def got_category(message: Message, state: FSMContext):
    category = message.text.strip()
    if not category:
        await message.answer("Iltimos, kategoriya nomini kiriting.")
        return
    await state.update_data(category=category)
    await message.answer(
        "🔢 <b>Variant raqamini kiriting</b>\n<i>(masalan: 1, 2, A, yakuniy)</i>",
        parse_mode="HTML",
    )
    await state.set_state(UploadStates.waiting_variant)


# ─── Step 2: Variant ─────────────────────────────────────────────────────────

@router.message(UploadStates.waiting_variant)
async def got_variant(message: Message, state: FSMContext):
    variant = message.text.strip()
    if not variant:
        await message.answer("Iltimos, variant raqamini kiriting.")
        return
    await state.update_data(variant=variant, photos=[])
    await message.answer(
        "📄 <b>Fayl formatini tanlang:</b>\n\n"
        "📋 <b>Klassik</b> — <code>+</code> va <code>=</code> belgilari bilan ajratilgan format\n"
        "📝 <b>Oddiy</b> — har bir savol bloki bo'sh qator bilan ajratiladi, "
        "to'g'ri javob oldiga <code>*</code> qo'yiladi",
        parse_mode="HTML",
        reply_markup=format_choice_kb(),
    )
    await state.set_state(UploadStates.choosing_format)


# ─── Step 3: Format choice ───────────────────────────────────────────────────

@router.callback_query(UploadStates.choosing_format, F.data.startswith("fmt:"))
async def chose_format(callback: CallbackQuery, state: FSMContext):
    fmt = callback.data.split(":", 1)[1]   # "classic" | "simple"
    await state.update_data(fmt=fmt)

    fmt_name = "Klassik (+ va =)" if fmt == "classic" else "Oddiy (bo'sh qator)"
    await callback.message.edit_text(
        f"✅ Format tanlandi: <b>{html.quote(fmt_name)}</b>",
        parse_mode="HTML",
    )

    # Show format hint
    if fmt == "classic":
        hint = (
            "📋 <b>Klassik format namunasi:</b>\n\n"
            "<pre>"
            "+\n"
            "Savol matni?\n"
            "=\n"
            "#To'g'ri javob\n"
            "=\n"
            "Javob 2\n"
            "=\n"
            "Javob 3\n"
            "=\n"
            "Javob 4\n"
            "+\n"
            "</pre>\n\n"
            "➕ <code>+</code> belgisi (1 yoki ko'proq) — savollar orasidagi chegara\n"
            "➖ <code>=</code> belgisi (1 yoki ko'proq) — javoblar orasidagi chegara\n"
            "<code>#</code> — to'g'ri javob belgisi (faqat bitta)"
        )
    else:
        hint = (
            "📝 <b>Oddiy format namunasi:</b>\n\n"
            "<pre>"
            "Savol matni?\n"
            "Javob 1\n"
            "*To'g'ri javob\n"
            "Javob 3\n"
            "Javob 4\n"
            "\n"
            "Ikkinchi savol?\n"
            "*To'g'ri javob\n"
            "Javob 2\n"
            "Javob 3\n"
            "Javob 4\n"
            "</pre>\n\n"
            "<code>*</code> — to'g'ri javob belgisi (faqat bitta)\n"
            "Bo'sh qator — savollar orasidagi chegara"
        )

    await callback.message.answer(
        hint,
        parse_mode="HTML",
        reply_markup=skip_or_cancel_kb(),
    )
    await state.set_state(UploadStates.waiting_photos)
    await callback.answer()


# ─── Step 4: Photos ──────────────────────────────────────────────────────────

@router.message(UploadStates.waiting_photos, F.text == SKIP_BTN)
async def skip_photos(message: Message, state: FSMContext):
    await _ask_for_file(message, state)


@router.message(UploadStates.waiting_photos, F.photo)
async def got_photo(message: Message, state: FSMContext):
    data   = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"✅ Rasm qabul qilindi ({len(photos)} ta).\n"
        "Yana rasm yuboring yoki faylni yuboring."
    )


@router.message(UploadStates.waiting_photos, F.document)
async def got_doc_in_photo_state(message: Message, state: FSMContext, bot: Bot):
    await _process_file(message, state, bot)


async def _ask_for_file(message: Message, state: FSMContext):
    await message.answer(
        "📎 <b>Endi faylni yuboring</b>\n\n"
        "Qabul qilinadigan formatlar: <code>.txt</code> <code>.docx</code> <code>.pdf</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(UploadStates.waiting_file)


# ─── Step 5: File ────────────────────────────────────────────────────────────

@router.message(UploadStates.waiting_file, F.document)
async def got_file(message: Message, state: FSMContext, bot: Bot):
    await _process_file(message, state, bot)


async def _process_file(message: Message, state: FSMContext, bot: Bot = None):
    if bot is None:
        bot = message.bot

    doc = message.document
    fname = (doc.file_name or "").lower()

    ext = next((e for e in SUPPORTED_EXTENSIONS if fname.endswith(e)), None)
    if ext is None:
        await message.answer(
            "❗ Faqat <code>.txt</code>, <code>.docx</code> yoki <code>.pdf</code> formatdagi fayl qabul qilinadi.",
            parse_mode="HTML",
        )
        return

    data     = await state.get_data()
    category = data.get("category", "Umumiy")
    variant  = data.get("variant",  "1")
    photos   = data.get("photos",   [])
    fmt      = data.get("fmt",      "classic")

    # Download file bytes
    tg_file       = await bot.get_file(doc.file_id)
    content_bytes = await bot.download_file(tg_file.file_path)
    raw_bytes     = content_bytes.read()

    # Extract plain text depending on file type
    try:
        text = _extract_text(raw_bytes, ext)
    except Exception as e:
        log.exception("Text extraction failed")
        await message.answer(f"❌ Faylni o'qib bo'lmadi: {html.quote(str(e))}", parse_mode="HTML")
        return

    if not text.strip():
        await message.answer("❌ Fayl bo'sh yoki o'qib bo'lmadi.")
        return

    # Parse questions
    if fmt == "classic":
        questions, errors = parse_classic(text)
    else:
        questions, errors = parse_simple(text)

    if errors:
        # Экранируем ошибки парсинга, чтобы не ломать HTML-разметку
        err_text = "\n".join(f"• {html.quote(e)}" for e in errors[:10])
        await message.answer(
            f"⚠️ <b>{len(errors)} ta xatolik topildi:</b>\n{err_text}\n\n"
            "Qolgan to'g'ri savollar saqlanadi.",
            parse_mode="HTML",
        )

    if not questions:
        if fmt == "classic":
            sample = "<pre>+\nSavol\n=\n#To'g'ri javob\n=\nJavob2\n=\nJavob3\n=\nJavob4\n+</pre>"
        else:
            sample = "<pre>Savol?\n*To'g'ri javob\nJavob2\nJavob3\nJavob4\n\nSavol 2?\n...</pre>"
        await message.answer(
            f"❌ Hech qanday savol topilmadi.\n\nFormat:\n{sample}",
            parse_mode="HTML",
        )
        return

    # Save to DB, distributing photos 1–2 per question
    photo_idx = 0
    saved     = 0
    for q in questions:
        fid1 = photos[photo_idx]     if photo_idx < len(photos) else None
        photo_idx += 1
        fid2 = photos[photo_idx]     if photo_idx < len(photos) else None
        photo_idx += 1

        await add_question(
            category = category,
            variant  = variant,
            question = q["question"],
            answers  = q["answers"],
            correct  = q["correct"],
            file_id  = fid1,
            file_id2 = fid2,
            added_by = message.from_user.id,
        )
        saved += 1

    await state.clear()
    from handlers.start import main_kb
    from handlers.group_quiz import send_group_launch_card

    bot_info     = await bot.get_me()
    bot_username = bot_info.username

    # Restore main keyboard
    await message.answer(
        f"✅ <b>{saved} ta savol saqlandi!</b>\n"
        f"🖼 Rasmlar: <b>{min(len(photos), saved * 2)} ta</b>",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )

    # Deep link card with group launch button
    await send_group_launch_card(
        message      = message,
        bot          = bot,
        category     = category,
        variant      = variant,
        total        = saved,
        bot_username = bot_username,
    )


# ─── Text extraction ─────────────────────────────────────────────────────────

def _extract_text(raw_bytes: bytes, ext: str) -> str:
    """Extract plain text from .txt / .docx / .pdf bytes."""

    if ext == ".txt":
        for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    if ext == ".docx":
        import docx
        doc = docx.Document(io.BytesIO(raw_bytes))
        return "\n".join(p.text for p in doc.paragraphs)

    if ext == ".pdf":
        import fitz  # PyMuPDF
        pdf  = fitz.open(stream=raw_bytes, filetype="pdf")
        parts = []
        for page in pdf:
            parts.append(page.get_text())
        pdf.close()
        return "\n".join(parts)

    return ""


# ─── Parser helpers ──────────────────────────────────────────────────────────

def _is_plus_sep(line: str) -> bool:
    """Line contains only '+' chars (and optional spaces), at least one '+'."""
    s = line.strip()
    return bool(s) and bool(re.fullmatch(r'[\+\s]+', s)) and '+' in s


def _is_eq_sep(line: str) -> bool:
    """Line contains only '=' chars (and optional spaces), at least one '='."""
    s = line.strip()
    return bool(s) and bool(re.fullmatch(r'[\=\s]+', s)) and '=' in s


# ─── Format 1: Classic ───────────────────────────────────────────────────────

def parse_classic(text: str):
    """
    Blocks separated by lines of '+' (any count).
    Inside a block, answers separated by lines of '=' (any count).
    Correct answer line starts with exactly one '#'.
    """
    questions: list[dict] = []
    errors:    list[str]  = []

    # Split into raw blocks by '+' separators
    raw_blocks: list[str] = []
    current: list[str]    = []
    for line in text.splitlines():
        if _is_plus_sep(line):
            if current:
                raw_blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        raw_blocks.append("\n".join(current))

    q_num = 0
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        q_num += 1

        # Split block into parts by '=' separators
        parts:  list[str] = []
        chunk:  list[str] = []
        for line in block.splitlines():
            if _is_eq_sep(line):
                parts.append("\n".join(chunk).strip())
                chunk = []
            else:
                chunk.append(line)
        parts.append("\n".join(chunk).strip())

        # Drop leading/trailing empty parts
        while parts and not parts[0]:
            parts.pop(0)
        while parts and not parts[-1]:
            parts.pop()

        if len(parts) != 5:
            errors.append(
                f"Savol #{q_num}: 5 qism kerak (savol + 4 javob), "
                f"lekin {len(parts)} ta topildi."
            )
            continue

        question_text = parts[0]
        raw_answers   = parts[1:]

        if not question_text:
            errors.append(f"Savol #{q_num}: savol matni bo'sh.")
            continue

        result = _extract_correct(raw_answers, q_num, marker="#")
        if isinstance(result, str):      # error message
            errors.append(result)
            continue

        answers, correct_idx = result
        if any(a == "" for a in answers):
            errors.append(f"Savol #{q_num}: ba'zi javoblar bo'sh.")
            continue

        questions.append({"question": question_text, "answers": answers, "correct": correct_idx})

    return questions, errors


# ─── Format 2: Simple (blank-line separated) ─────────────────────────────────

def parse_simple(text: str):
    """
    Blocks separated by one or more blank lines.
    First non-empty line of a block = question.
    Remaining lines = answers (4 required).
    Correct answer starts with '*'.
    """
    questions: list[dict] = []
    errors:    list[str]  = []

    # Split into blocks by blank lines
    raw_blocks: list[list[str]] = []
    current:    list[str]       = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                raw_blocks.append(current)
                current = []
        else:
            current.append(line.strip())
    if current:
        raw_blocks.append(current)

    q_num = 0
    for block in raw_blocks:
        block = [l for l in block if l]
        if not block:
            continue
        q_num += 1

        if len(block) < 5:
            errors.append(
                f"Savol #{q_num}: kamida 5 qator kerak "
                f"(savol + 4 javob), lekin {len(block)} ta topildi."
            )
            continue

        question_text = block[0]
        raw_answers   = block[1:5]   # exactly 4 answers

        if len(block) > 5:
            errors.append(
                f"Savol #{q_num}: 4 tadan ortiq javob topildi — "
                f"faqat birinchi 4 tasi qabul qilindi."
            )

        result = _extract_correct(raw_answers, q_num, marker="*")
        if isinstance(result, str):
            errors.append(result)
            continue

        answers, correct_idx = result
        questions.append({"question": question_text, "answers": answers, "correct": correct_idx})

    return questions, errors


# ─── Shared helper ───────────────────────────────────────────────────────────

def _extract_correct(raw_answers: list[str], q_num: int, marker: str):
    """
    Find the answer line that starts with `marker` (exactly one character).
    Returns (answers_list, correct_index) or an error string.
    """
    correct_idx = None
    answers:    list[str] = []
    for i, ans in enumerate(raw_answers):
        if ans.startswith(marker):
            if correct_idx is not None:
                return (
                    f"Savol #{q_num}: bir nechta to'g'ri javob "
                    f"({marker}) topildi."
                )
            correct_idx = i
            answers.append(ans[len(marker):].strip())
        else:
            answers.append(ans.strip())

    if correct_idx is None:
        return (
            f"Savol #{q_num}: to'g'ri javob belgilanmagan "
            f"('{marker}' belgisini to'g'ri javob oldiga qo'ying)."
        )
    return answers, correct_idx