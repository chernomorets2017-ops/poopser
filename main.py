import asyncio
import json
import os
import sys

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)

from parser import get_new_posts
from notifier import send_posts
from payments import (
    init_user,
    has_access,
    get_status,
    activate_subscription,
    SUB_PRICE_RUB,
)

TOKEN = os.environ["BOT_TOKEN"]
MINI_APP_URL = os.environ["MINI_APP_URL"]
# Получить в BotFather → /mybots → Payments → ЮКасса (тест или боевой)
PAYMENT_PROVIDER_TOKEN = os.environ["PAYMENT_PROVIDER_TOKEN"]

USERS_FILE = "data/users.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ── Хелперы ────────────────────────────────────────────────────────────────

def load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="⚙️ Настройки и подписка",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])


# ── /start ─────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)

    if uid not in users:
        users[uid] = init_user({
            "active": True,
            "channels": [],
            "keywords": [],
            "ai": {},
        })
        save_users(users)

    status = get_status(users[uid])

    if status["type"] == "trial":
        text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"🎁 У тебя <b>3 дня бесплатного доступа</b>.\n"
            f"{status['detail']}\n\n"
            f"Настрой каналы и ключевые слова в меню ниже:"
        )
    elif status["type"] == "subscribed":
        text = (
            f"👋 С возвращением!\n\n"
            f"✅ Подписка активна — {status['detail']}\n\n"
            f"Открой настройки чтобы изменить каналы:"
        )
    else:
        text = (
            f"👋 Привет!\n\n"
            f"❌ Твой пробный период истёк.\n"
            f"Оформи подписку за <b>{SUB_PRICE_RUB}₽/мес</b> чтобы продолжить:"
        )

    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")


# ── /status ────────────────────────────────────────────────────────────────

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)
    cfg = users.get(uid, {})
    if not cfg:
        await message.answer("Сначала напиши /start")
        return

    status = get_status(cfg)
    channels = ", ".join(cfg.get("channels", [])) or "не заданы"
    keywords = ", ".join(cfg.get("keywords", [])) or "все посты"
    ai = cfg.get("ai", {})
    ai_status = f"вкл ({ai.get('style', 'hype')})" if ai.get("enabled") else "выкл"

    await message.answer(
        f"<b>📊 Твой статус</b>\n\n"
        f"{status['label']} — {status['detail']}\n\n"
        f"📢 Каналы: {channels}\n"
        f"🔍 Слова: {keywords}\n"
        f"🤖 Нейронка: {ai_status}",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ── /stop ──────────────────────────────────────────────────────────────────

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)
    if uid in users:
        users[uid]["active"] = False
        save_users(users)
    await message.answer("⏸ Рассылка остановлена. Напиши /start чтобы включить снова.")


# ── Данные из Mini App ─────────────────────────────────────────────────────

@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        users = load_users()
        uid = str(message.from_user.id)

        # Действие: запрос на оплату
        if data.get("action") == "pay":
            await send_invoice(message.chat.id)
            return

        # Действие: сохранение настроек
        if uid not in users:
            users[uid] = init_user({})

        users[uid].update({
            "active": True,
            "channels": data.get("channels", []),
            "keywords": data.get("keywords", []),
            "ai": {
                "enabled": data.get("ai_enabled", False),
                "style": data.get("ai_style", "hype"),
                "custom_prompt": data.get("ai_prompt", ""),
            },
        })
        save_users(users)

        channels_list = ", ".join(data.get("channels", [])) or "—"
        ai_status = "🤖 вкл" if data.get("ai_enabled") else "выкл"
        await message.answer(
            f"✅ <b>Настройки сохранены!</b>\n\n"
            f"📢 Каналы: {channels_list}\n"
            f"🤖 Нейронка: {ai_status}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ── Оплата через Telegram Payments (ЮКасса) ───────────────────────────────

async def send_invoice(chat_id: int):
    """Отправляет инвойс пользователю."""
    await bot.send_invoice(
        chat_id=chat_id,
        title="Подписка на парсер каналов",
        description=(
            f"Доступ на 30 дней: неограниченные каналы, "
            f"нейронная переработка постов, фильтры по словам."
        ),
        payload="sub_30days",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Подписка 30 дней", amount=SUB_PRICE_RUB * 100)],
        photo_url="https://i.imgur.com/placeholder.png",  # можно убрать
        need_email=False,
        need_phone_number=False,
        is_flexible=False,
    )


@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    """Telegram спрашивает подтвердить платёж — всегда OK."""
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    """Платёж прошёл — активируем подписку."""
    users = load_users()
    uid = str(message.from_user.id)

    if uid not in users:
        users[uid] = init_user({})

    users[uid] = activate_subscription(users[uid])
    save_users(users)

    status = get_status(users[uid])
    await message.answer(
        f"🎉 <b>Оплата прошла!</b>\n\n"
        f"✅ Подписка активна — {status['detail']}\n\n"
        f"Посты уже полетят в ближайшие 30 минут.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ── Запуск парсера ─────────────────────────────────────────────────────────

async def run_parser():
    users = load_users()
    all_channels = set()

    for cfg in users.values():
        if cfg.get("active") and has_access(cfg):
            all_channels.update(cfg.get("channels", []))

    if not all_channels:
        print("Нет активных каналов с доступом")
        await bot.session.close()
        return

    print(f"Парсим каналы: {all_channels}")
    posts = get_new_posts(list(all_channels), [])

    if posts:
        print(f"Новых постов: {len(posts)}")
        await send_posts(bot, posts)
    else:
        print("Новых постов нет")

    await bot.session.close()


# ── Обработка платёжных апдейтов (короткий polling) ───────────────────────

async def run_payment_polling():
    """
    Запускается отдельным workflow каждые 5 минут.
    Получает обновления боту и обрабатывает платежи + настройки.
    Завершается через 55 секунд (чтобы не превысить 1 мин).
    """
    import asyncio as aio

    async def polling_task():
        await dp.start_polling(bot, polling_timeout=10)

    try:
        await aio.wait_for(polling_task(), timeout=55)
    except aio.TimeoutError:
        pass
    finally:
        await bot.session.close()


# ── Точка входа ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"

    if mode == "parse":
        asyncio.run(run_parser())
    elif mode == "payments":
        asyncio.run(run_payment_polling())
    else:
        # Полный режим для локального запуска
        asyncio.run(dp.start_polling(bot))