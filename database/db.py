import aiosqlite
import json

DB_PATH = "database/quiz.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT    NOT NULL DEFAULT 'Umumiy',
                variant     TEXT    NOT NULL DEFAULT '1',
                question    TEXT    NOT NULL,
                answers     TEXT    NOT NULL,
                correct     INTEGER NOT NULL,
                file_id     TEXT,
                file_id2    TEXT,
                added_by    INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                score       INTEGER NOT NULL,
                total       INTEGER NOT NULL,
                category    TEXT,
                variant     TEXT,
                finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_uploads (
                user_id     INTEGER PRIMARY KEY,
                file_ids    TEXT,
                category    TEXT,
                variant     TEXT,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ── Групповые сессии ──────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       INTEGER NOT NULL,
                owner_id      INTEGER NOT NULL,
                category      TEXT    NOT NULL,
                variant       TEXT    NOT NULL,
                questions     TEXT    NOT NULL,   -- JSON list of question ids
                current_idx   INTEGER NOT NULL DEFAULT 0,
                is_active     INTEGER NOT NULL DEFAULT 1,
                timer_seconds INTEGER NOT NULL DEFAULT 30,
                started_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ответы участников в групповом режиме
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_answers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL,
                question_idx INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                first_name  TEXT,
                chosen      INTEGER NOT NULL,   -- 0..3
                is_correct  INTEGER NOT NULL,   -- 0 or 1
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, question_idx, user_id)
            )
        """)
        await db.commit()


# ─── questions ────────────────────────────────────────────────────────────────

async def add_question(category, variant, question, answers, correct,
                       file_id=None, file_id2=None, added_by=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO questions
               (category, variant, question, answers, correct, file_id, file_id2, added_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (category, variant, question, json.dumps(answers, ensure_ascii=False),
             correct, file_id, file_id2, added_by)
        )
        await db.commit()


async def get_questions(category=None, variant=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category and variant:
            cur = await db.execute(
                "SELECT * FROM questions WHERE category=? AND variant=?",
                (category, variant)
            )
        elif category:
            cur = await db.execute(
                "SELECT * FROM questions WHERE category=?", (category,)
            )
        else:
            cur = await db.execute("SELECT * FROM questions")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT DISTINCT category, variant FROM questions ORDER BY category, variant"
        )
        rows = await cur.fetchall()
    return rows


# ─── results ──────────────────────────────────────────────────────────────────

async def save_result(user_id, username, score, total, category, variant):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO results (user_id, username, score, total, category, variant)
               VALUES (?,?,?,?,?,?)""",
            (user_id, username, score, total, category, variant)
        )
        await db.commit()


async def get_user_results(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM results WHERE user_id=? ORDER BY finished_at DESC LIMIT 20",
            (user_id,)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ─── pending uploads ──────────────────────────────────────────────────────────

async def set_pending(user_id, file_ids: list, category: str, variant: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO pending_uploads (user_id, file_ids, category, variant)
               VALUES (?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                   file_ids=excluded.file_ids,
                   category=excluded.category,
                   variant=excluded.variant,
                   updated_at=CURRENT_TIMESTAMP""",
            (user_id, json.dumps(file_ids), category, variant)
        )
        await db.commit()


async def get_pending(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM pending_uploads WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
    if row:
        d = dict(row)
        d["file_ids"] = json.loads(d["file_ids"])
        return d
    return None


async def clear_pending(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_uploads WHERE user_id=?", (user_id,))
        await db.commit()


# ─── group sessions ───────────────────────────────────────────────────────────

async def create_group_session(chat_id, owner_id, category, variant,
                                question_ids: list, timer_seconds=30):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO group_sessions
               (chat_id, owner_id, category, variant, questions, timer_seconds)
               VALUES (?,?,?,?,?,?)""",
            (chat_id, owner_id, category, variant,
             json.dumps(question_ids), timer_seconds)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_group_session(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM group_sessions WHERE chat_id=? AND is_active=1",
            (chat_id,)
        )
        row = await cur.fetchone()
    if row:
        d = dict(row)
        d["questions"] = json.loads(d["questions"])
        return d
    return None


async def update_group_session_idx(session_id, new_idx):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_sessions SET current_idx=? WHERE id=?",
            (new_idx, session_id)
        )
        await db.commit()


async def close_group_session(session_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_sessions SET is_active=0 WHERE id=?",
            (session_id,)
        )
        await db.commit()


async def save_group_answer(session_id, question_idx, user_id,
                             username, first_name, chosen, is_correct):
    """Returns True if saved, False if already answered (duplicate)."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO group_answers
                   (session_id, question_idx, user_id, username, first_name, chosen, is_correct)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, question_idx, user_id,
                 username, first_name, chosen, is_correct)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # already answered


async def get_group_answers(session_id, question_idx):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM group_answers
               WHERE session_id=? AND question_idx=?
               ORDER BY answered_at""",
            (session_id, question_idx)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_group_scoreboard(session_id):
    """Returns list of (first_name, username, correct_count) sorted by score."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT first_name, username, user_id,
                      SUM(is_correct) as correct,
                      COUNT(*) as total
               FROM group_answers
               WHERE session_id=?
               GROUP BY user_id
               ORDER BY correct DESC""",
            (session_id,)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
