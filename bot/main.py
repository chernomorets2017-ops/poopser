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
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    LabeledPrice,
)

from parser import get_new_posts
from notifier import send_posts
from payments import (
    init_user,
    has_access,
    get_status,
    activate_subscription,
    apply_promo,
    is_admin,
    SUB_PRICE_RUB,
    SUB_DAYS,
)

TOKEN = os.environ["BOT_TOKEN"]
MINI_APP_URL = os.environ["MINI_APP_URL"]
PAYMENT_PROVIDER_TOKEN = os.environ["PAYMENT_PROVIDER_TOKEN"]

USERS_FILE = "data/users.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()


def load_users() -> dict:
    with open(USERS_FILE) as f:
        return json.load(f)


def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


# ── ВАЖНО: ReplyKeyboardMarkup с KeyboardButton — только так работает sendData ──
def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="⚙️ Настройки и подписка",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ]],
        resize_keyboard=True,
    )


# ── /start ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)
    username = message.from_user.username or ""

    # Обработка deep link: /start pay
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1] == "pay":
        await send_invoice(message.chat.id)
        return

    if uid not in users:
        users[uid] = init_user({"active": True, "channels": [], "keywords": [], "ai": {}}, username)
        save_users(users)
    elif is_admin(username) and not users[uid].get("is_admin"):
        users[uid] = init_user(users[uid], username)
        save_users(users)

    status = get_status(users[uid])

    if status["type"] == "admin":
        text = "👑 Привет, Саша! Полный доступ навсегда.\n\n/promo — управление промокодами\n/status — твой статус"
    elif status["type"] == "trial":
        text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"🎁 <b>3 дня бесплатного доступа.</b> {status['detail']}\n\n"
            f"Есть промокод? /promo КОД\n"
            f"Оплатить подписку: /pay\n\n"
            f"👇 Нажми кнопку чтобы настроить:"
        )
    elif status["type"] == "subscribed":
        text = (
            f"👋 С возвращением!\n\n"
            f"✅ Подписка активна — {status['detail']}\n\n"
            f"👇 Нажми кнопку чтобы изменить настройки:"
        )
    else:
        text = (
            f"👋 Привет!\n\n"
            f"❌ Пробный период истёк.\n"
            f"Оплати подписку: /pay\n"
            f"Есть промокод? /promo КОД\n\n"
            f"👇 Нажми кнопку:"
        )

    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")


# ── /pay — прямая оплата ─────────────────────────────────────────────────────

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    await send_invoice(message.chat.id)


# ── /status ──────────────────────────────────────────────────────────────────

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
        f"🤖 Нейронка: {ai_status}\n\n"
        f"Оплатить/продлить: /pay",
        parse_mode="HTML",
    )


# ── /stop ─────────────────────────────────────────────────────────────────────

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)
    if uid in users:
        users[uid]["active"] = False
        save_users(users)
    await message.answer("⏸ Рассылка остановлена. /start чтобы включить снова.")


# ── /promo ────────────────────────────────────────────────────────────────────

@dp.message(Command("promo"))
async def cmd_promo(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "🎟 Введи промокод так:\n\n<code>/promo ТВОЙКОД</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip()
    users = load_users()
    uid = str(message.from_user.id)

    if uid not in users:
        users[uid] = init_user({"active": True, "channels": [], "keywords": [], "ai": {}})

    updated_user, result = apply_promo(users[uid], code)
    users[uid] = updated_user
    save_users(users)

    if result["ok"] and result.get("free"):
        await message.answer(result["message"], reply_markup=get_main_keyboard())
    elif result["ok"]:
        discount = result["discount"]
        price = result["price"]
        days = result["days"]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=f"💳 Оплатить {price}₽ (скидка {discount}%)",
                callback_data=f"pay_promo:{code}:{price}:{days}"
            )
        ]])
        await message.answer(result["message"], reply_markup=kb)
    else:
        await message.answer(result["message"])


@dp.callback_query(F.data.startswith("pay_promo:"))
async def pay_with_promo(callback: types.CallbackQuery):
    _, code, price_str, days_str = callback.data.split(":")
    price = int(price_str)
    days = int(days_str)
    await callback.answer()
    await send_invoice(callback.message.chat.id, price=price, days=days, label=f"Подписка со скидкой ({code})")


# ── Данные из Mini App ────────────────────────────────────────────────────────

@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        users = load_users()
        uid = str(message.from_user.id)

        # Запрос оплаты из Mini App
        if data.get("action") == "pay":
            await send_invoice(message.chat.id)
            return

        # Промокод из Mini App
        if data.get("action") == "promo":
            code = data.get("code", "")
            if uid not in users:
                users[uid] = init_user({})
            updated_user, result = apply_promo(users[uid], code)
            users[uid] = updated_user
            save_users(users)
            await message.answer(result["message"])
            return

        # Сохранение настроек
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


# ── Оплата через Telegram Payments ───────────────────────────────────────────

async def send_invoice(chat_id: int, price: int = SUB_PRICE_RUB, days: int = SUB_DAYS, label: str = "Подписка 30 дней"):
    await bot.send_invoice(
        chat_id=chat_id,
        title="Подписка на парсер каналов",
        description=f"Доступ на {days} дней: каналы, нейронка, фильтры по словам.",
        payload=f"sub_{days}days",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=label, amount=price * 100)],
        need_email=False,
        need_phone_number=False,
        is_flexible=False,
    )


@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    users = load_users()
    uid = str(message.from_user.id)
    payload = message.successful_payment.invoice_payload

    days = SUB_DAYS
    try:
        days = int(payload.replace("sub_", "").replace("days", ""))
    except Exception:
        pass

    if uid not in users:
        users[uid] = init_user({})

    users[uid] = activate_subscription(users[uid], days=days)
    save_users(users)

    status = get_status(users[uid])
    await message.answer(
        f"🎉 <b>Оплата прошла!</b>\n\n"
        f"✅ Подписка активна — {status['detail']}\n\n"
        f"Посты полетят в течение 30 минут.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ── Парсер ────────────────────────────────────────────────────────────────────

async def run_parser():
    users = load_users()
    all_channels = set()
    for cfg in users.values():
        if cfg.get("active") and has_access(cfg):
            all_channels.update(cfg.get("channels", []))

    if not all_channels:
        print("Нет активных каналов")
        await bot.session.close()
        return

    print(f"Парсим: {all_channels}")
    posts = get_new_posts(list(all_channels), [])

    if posts:
        print(f"Новых постов: {len(posts)}")
        await send_posts(bot, posts)
    else:
        print("Новых постов нет")

    await bot.session.close()


async def run_payment_polling():
    import asyncio as aio
    async def polling_task():
        await dp.start_polling(bot, polling_timeout=10)
    try:
        await aio.wait_for(polling_task(), timeout=55)
    except aio.TimeoutError:
        pass
    finally:
        await bot.session.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if mode == "parse":
        asyncio.run(run_parser())
    elif mode == "payments":
        asyncio.run(run_payment_polling())
    else:
        asyncio.run(dp.start_polling(bot))