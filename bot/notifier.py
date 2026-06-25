import asyncio
import json
from aiogram import Bot
from rewriter import rewrite_post
from payments import has_access

USERS_FILE = "data/users.json"


def load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


async def send_posts(bot: Bot, posts: list):
    users = load_users()

    for user_id, config in users.items():
        # Проверяем доступ (триал или подписка)
        if not has_access(config):
            print(f"Пользователь {user_id} — нет доступа, пропускаем")
            continue

        if not config.get("active"):
            continue

        user_channels = config.get("channels", [])
        user_keywords = config.get("keywords", [])
        ai_config = config.get("ai", {})
        use_ai = ai_config.get("enabled", False)
        ai_style = ai_config.get("style", "hype")
        ai_prompt = ai_config.get("custom_prompt", "")

        for post in posts:
            if post["channel"] not in user_channels:
                continue
            if user_keywords:
                if not any(kw.lower() in post["text"].lower() for kw in user_keywords):
                    continue

            display_text = post["text"]
            ai_label = ""

            if use_ai and display_text.strip():
                display_text = await rewrite_post(display_text, ai_style, ai_prompt)
                ai_label = "🤖 <i>Переписано нейронкой</i>\n\n"

            try:
                caption = (
                    f"📢 <b>@{post['channel']}</b>\n\n"
                    f"{ai_label}"
                    f"{display_text[:900]}\n\n"
                    f"<a href='{post['url']}'>→ Оригинал</a>"
                )
                if post["photo"]:
                    await bot.send_photo(
                        int(user_id), post["photo"],
                        caption=caption, parse_mode="HTML",
                    )
                else:
                    await bot.send_message(
                        int(user_id), caption, parse_mode="HTML",
                    )
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки {user_id}: {e}")
