import asyncio
import json
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from rewriter import rewrite_post
from payments import has_access

USERS_FILE = "data/users.json"


def load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


def get_destination(config: dict, user_id: str) -> str:
    """
    Возвращает chat_id куда слать посты.
    Если пользователь указал свой канал — шлём туда.
    Иначе — в личку.
    """
    dest = config.get("dest_channel", "").strip()
    if dest:
        # Нормализуем: @channel или -100123456789
        if dest.startswith("-100"):
            return dest  # числовой ID канала
        if not dest.startswith("@"):
            dest = "@" + dest
        return dest
    return user_id  # личка


async def send_posts(bot: Bot, posts: list):
    users = load_users()

    for user_id, config in users.items():
        if not has_access(config):
            print(f"Пользователь {user_id} — нет доступа, пропускаем")
            continue

        if not config.get("active"):
            continue

        user_channels  = config.get("channels", [])
        user_keywords  = config.get("keywords", [])
        ai_config      = config.get("ai", {})
        use_ai         = ai_config.get("enabled", False)
        ai_style       = ai_config.get("style", "hype")
        ai_prompt      = ai_config.get("custom_prompt", "")
        destination    = get_destination(config, user_id)

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
                ai_label = "🤖 <i>Нейронка</i>\n\n"

            try:
                caption = (
                    f"📢 <b>@{post['channel']}</b>\n\n"
                    f"{ai_label}"
                    f"{display_text[:900]}\n\n"
                    f"<a href='{post['url']}'>→ Оригинал</a>"
                )

                # Пробуем отправить в нужное место
                target = int(destination) if destination.lstrip("-").isdigit() else destination

                if post["photo"]:
                    await bot.send_photo(target, post["photo"], caption=caption, parse_mode="HTML")
                else:
                    await bot.send_message(target, caption, parse_mode="HTML")

                await asyncio.sleep(0.1)

            except TelegramForbiddenError:
                # Бот не админ в канале — уведомляем пользователя в личку
                await _notify_user_error(
                    bot, user_id, destination,
                    "❌ Бот не может постить в канал <b>{dest}</b>.\n\n"
                    "Добавь бота как администратора в канал и попробуй снова.\n"
                    "Или убери канал в настройках — посты будут приходить сюда."
                )
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    await _notify_user_error(
                        bot, user_id, destination,
                        "❌ Канал <b>{dest}</b> не найден.\n\n"
                        "Проверь юзернейм канала в настройках."
                    )
                else:
                    print(f"Ошибка отправки в {destination}: {e}")
            except Exception as e:
                print(f"Ошибка отправки {user_id} → {destination}: {e}")


async def _notify_user_error(bot: Bot, user_id: str, dest: str, text: str):
    """Шлёт ошибку пользователю в личку (один раз)."""
    try:
        await bot.send_message(
            int(user_id),
            text.format(dest=dest),
            parse_mode="HTML",
        )
    except Exception:
        pass