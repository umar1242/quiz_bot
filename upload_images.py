import asyncio
import json
from aiogram import Bot
from aiogram.types import BufferedInputFile
from config import BOT_TOKEN

YOUR_ID = 1043620738

async def upload():
    bot = Bot(token=BOT_TOKEN)

    # Вопросы с двумя картинками
    multi = {2, 5, 16, 18, 19, 25, 29}

    # Ключи ответов (0=A, 1=B, 2=C, 3=D)
    answers = {
        1:1, 2:2, 3:3, 4:2, 5:2, 6:0, 7:3, 8:0, 9:0, 10:0,
        11:1, 12:1, 13:1, 14:0, 15:3, 16:0, 17:0, 18:2, 19:2, 20:0,
        21:0, 22:0, 23:1, 24:3, 25:1, 26:0, 27:3, 28:1, 29:3, 30:2
    }

    # Загружаем существующий questions.json
    try:
        with open("data/questions.json", encoding="utf-8") as f:
            results = json.load(f)
    except:
        results = []

    for q_num in range(1, 31):
        correct = answers[q_num]

        if q_num in multi:
            # Два файла — отправляем группой
            files = [
                f"data/images/v2_q{q_num}.png",
                f"data/images/v2_q{q_num},2.png"
            ]
            media = []
            file_ids = []
            for path in files:
                with open(path, "rb") as f:
                    photo = BufferedInputFile(f.read(), filename=path)
                    msg = await bot.send_photo(YOUR_ID, photo)
                    file_ids.append(msg.photo[-1].file_id)

            results.append({
                "category": "Биология",
                "variant": "2",
                "file_id": file_ids[0],
                "file_id2": file_ids[1],
                "correct": correct
            })
            print(f"✅ Q{q_num} (2 фото): {'ABCD'[correct]}")
        else:
            path = f"data/images/v2_q{q_num}.png"
            with open(path, "rb") as f:
                photo = BufferedInputFile(f.read(), filename=path)
                msg = await bot.send_photo(YOUR_ID, photo)
                file_id = msg.photo[-1].file_id

            results.append({
                "category": "Биология",
                "variant": "2",
                "file_id": file_id,
                "correct": correct
            })
            print(f"✅ Q{q_num}: {'ABCD'[correct]}")

    with open("data/questions.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Готово! Всего вопросов в базе: {len(results)}")
    await bot.session.close()

asyncio.run(upload())