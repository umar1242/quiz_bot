"""
handlers/stats.py
"""

from aiogram import Router, F
from aiogram.types import Message
from database.db import get_user_results

router = Router()


@router.message(F.text == "📊 Mening natijalarim")
async def cmd_stats(message: Message):
    results = await get_user_results(message.from_user.id)

    if not results:
        await message.answer("📭 Siz hali hech qanday test yechmagansiz.")
        return

    lines = ["📊 *Sizning natijalaringiz:*\n"]
    for r in results[:10]:
        pct = round(r["score"] / r["total"] * 100) if r["total"] else 0
        lines.append(
            f"• *{r['category']}* (var. {r['variant']}): "
            f"{r['score']}/{r['total']} — {pct}%"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")
