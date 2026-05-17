import aiosqlite

DB_PATH = "database/quiz.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                category TEXT,
                variant TEXT,
                score INTEGER,
                total INTEGER,
                time_spent INTEGER,
                wrong_questions TEXT,
                finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def register_user(telegram_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
            (telegram_id, name)
        )
        await db.commit()

async def save_result(telegram_id: int, category: str, variant: str,
                      score: int, total: int, time_spent: int, wrong_questions: list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO results
               (telegram_id, category, variant, score, total, time_spent, wrong_questions)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, category, variant, score, total, time_spent,
             ",".join(map(str, wrong_questions)))
        )
        await db.commit()

async def get_user_stats(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*), ROUND(AVG(score * 100.0 / total), 1),
                   MAX(score * 100.0 / total)
            FROM results WHERE telegram_id = ?
        """, (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_leaderboard():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT u.name, COUNT(r.id) as attempts,
                   ROUND(AVG(r.score * 100.0 / r.total), 1) as avg_score
            FROM results r
            JOIN users u ON u.telegram_id = r.telegram_id
            GROUP BY r.telegram_id
            ORDER BY avg_score DESC
            LIMIT 5
        """) as cursor:
            return await cursor.fetchall()