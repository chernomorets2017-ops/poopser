"""
Логика подписки и триала.

Структура записи пользователя в users.json:
{
  "active": true,
  "channels": [...],
  "keywords": [...],
  "ai": {...},
  "trial_until": "2024-01-05T12:00:00",   # дата окончания триала (ISO)
  "sub_until": "2024-02-01T12:00:00",      # дата окончания подписки (ISO или null)
  "sub_active": false                       # флаг активной подписки
}
"""

from datetime import datetime, timedelta, timezone

TRIAL_DAYS = 3
SUB_DAYS = 30
SUB_PRICE_RUB = 200


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Инициализация нового пользователя ──────────────────────────────────────

def init_user(user_data: dict) -> dict:
    """Добавляет поля подписки если их нет (новый пользователь)."""
    if "trial_until" not in user_data:
        user_data["trial_until"] = iso(now() + timedelta(days=TRIAL_DAYS))
    if "sub_until" not in user_data:
        user_data["sub_until"] = None
    if "sub_active" not in user_data:
        user_data["sub_active"] = False
    return user_data


# ── Проверка доступа ────────────────────────────────────────────────────────

def has_access(user_data: dict) -> bool:
    """Есть ли у пользователя доступ (триал или подписка)."""
    # Активная оплаченная подписка
    if user_data.get("sub_active") and user_data.get("sub_until"):
        if from_iso(user_data["sub_until"]) > now():
            return True

    # Триал ещё не истёк
    trial_until = user_data.get("trial_until")
    if trial_until and from_iso(trial_until) > now():
        return True

    return False


def get_status(user_data: dict) -> dict:
    """Возвращает словарь со статусом для отображения."""
    sub_until = user_data.get("sub_until")
    trial_until = user_data.get("trial_until")
    sub_active = user_data.get("sub_active", False)

    # Подписка активна
    if sub_active and sub_until and from_iso(sub_until) > now():
        days_left = (from_iso(sub_until) - now()).days
        return {
            "type": "subscribed",
            "label": "✅ Подписка активна",
            "detail": f"Осталось {days_left} дн.",
            "until": sub_until,
            "can_pay": True,   # можно продлить заранее
        }

    # Триал
    if trial_until and from_iso(trial_until) > now():
        hours_left = int((from_iso(trial_until) - now()).total_seconds() / 3600)
        days_left = hours_left // 24
        label = f"{days_left} дн." if days_left > 0 else f"{hours_left} ч."
        return {
            "type": "trial",
            "label": "🎁 Пробный период",
            "detail": f"Осталось {label}",
            "until": trial_until,
            "can_pay": True,
        }

    # Истекло
    return {
        "type": "expired",
        "label": "❌ Подписка истекла",
        "detail": "Оплати чтобы продолжить",
        "until": None,
        "can_pay": True,
    }


# ── Активация подписки после оплаты ────────────────────────────────────────

def activate_subscription(user_data: dict) -> dict:
    """Вызывается после успешной оплаты."""
    # Если есть действующая подписка — продлеваем от её конца
    sub_until = user_data.get("sub_until")
    if sub_until and user_data.get("sub_active") and from_iso(sub_until) > now():
        new_until = from_iso(sub_until) + timedelta(days=SUB_DAYS)
    else:
        new_until = now() + timedelta(days=SUB_DAYS)

    user_data["sub_until"] = iso(new_until)
    user_data["sub_active"] = True
    user_data["active"] = True
    return user_data
