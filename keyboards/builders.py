from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from habits.registry import HABIT_REGISTRY, SELECTABLE_HABIT_KEYS
from heroes.data import HEROES, HERO_KEYS_ORDERED


# ── Onboarding ────────────────────────────────────────────────────────────────

def kb_start() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Начать", callback_data="onboarding:start")
    return kb.as_markup()


def kb_contact() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📱 Поделиться контактом", request_contact=True)
    kb.button(text="Пропустить →")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_goal() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for text, data in [
        ("🕐 Наладить режим", "goal:routine"),
        ("🏃 Больше двигаться", "goal:move_more"),
        ("⚖️ Похудеть", "goal:lose_weight"),
        ("🧘 Снизить стресс", "goal:reduce_stress"),
        ("🚫 Избавиться от вредных привычек", "goal:quit_bad_habits"),
    ]:
        kb.button(text=text, callback_data=data)
    kb.adjust(1)
    return kb.as_markup()


def kb_weight_goal() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Нет, просто хочу наладить привычки", callback_data="wgoal:none")
    kb.button(text="⬇️ Хочу похудеть", callback_data="wgoal:lose")
    kb.button(text="⬆️ Хочу набрать вес", callback_data="wgoal:gain")
    kb.adjust(1)
    return kb.as_markup()


def kb_habits(selected: list[str], show_weight: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    keys = SELECTABLE_HABIT_KEYS + (["weight"] if show_weight else [])
    for key in keys:
        habit = HABIT_REGISTRY.get(key)
        check = "✅ " if key in selected else ""
        if habit:
            kb.button(text=f"{check}{habit.emoji} {habit.display_name}", callback_data=f"habit_toggle:{key}")
        else:
            kb.button(text=f"{check}⚖️ Вес", callback_data=f"habit_toggle:{key}")
    kb.button(text="➡️ Продолжить", callback_data="habit_toggle:done")
    kb.adjust(2)
    return kb.as_markup()


def kb_timezone() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    offsets = [-5, -3, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]
    for off in offsets:
        sign = "+" if off >= 0 else ""
        kb.button(text=f"UTC{sign}{off}", callback_data=f"tz:{off}")
    kb.adjust(4)
    return kb.as_markup()


def kb_hero() -> InlineKeyboardMarkup:
    """Hero selection keyboard grouped by category."""
    kb = InlineKeyboardBuilder()
    category_labels = {
        "chill": "😌 Chill",
        "funny": "😂 Funny",
        "cute": "🥰 Cute",
        "energy": "⚡ Energy",
        "smart": "🧠 Smart",
    }
    current_cat = None
    for key in HERO_KEYS_ORDERED:
        hero = HEROES[key]
        if hero.category != current_cat:
            current_cat = hero.category
        kb.button(
            text=f"{hero.emoji} {hero.name}",
            callback_data=f"hero:{key}",
        )
    kb.adjust(2)
    return kb.as_markup()


def kb_remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ── Check-in ──────────────────────────────────────────────────────────────────

def kb_start_checkin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отметить привычки", callback_data="checkin:begin")
    return kb.as_markup()


def kb_scale(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=str(i), callback_data=f"{prefix}:{i}")
    kb.adjust(5)
    return kb.as_markup()


def kb_yes_no(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Да", callback_data=yes_data)
    kb.button(text="✅ Нет", callback_data=no_data)
    kb.adjust(2)
    return kb.as_markup()


# ── Weight ────────────────────────────────────────────────────────────────────

def kb_start_weight() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚖️ Ввести вес", callback_data="weight:begin")
    return kb.as_markup()


# ── Subscription ──────────────────────────────────────────────────────────────

def kb_subscribe() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Месяц — 249 ₽", callback_data="sub:monthly")
    kb.button(text="💎 Год — 1790 ₽", callback_data="sub:yearly")
    kb.adjust(1)
    return kb.as_markup()


# ── Academy ───────────────────────────────────────────────────────────────────

def kb_academy(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏃 Узнать про беговую академию", url=url)
    return kb.as_markup()


# ── Progress card share ───────────────────────────────────────────────────────

def kb_share_report() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Поделиться", switch_inline_query="..")
    return kb.as_markup()


# ── Settings ──────────────────────────────────────────────────────────────────

def kb_settings() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🕐 Время чек-ина", callback_data="settings:checkin_time")
    kb.button(text="😴 Время сна", callback_data="settings:sleep_time")
    kb.button(text="🌍 Часовой пояс", callback_data="settings:timezone")
    kb.button(text="🦫 Сменить героя", callback_data="settings:hero")
    kb.button(text="✏️ Изменить привычки", callback_data="settings:habits")
    kb.adjust(2)
    return kb.as_markup()


# ── Feedback ──────────────────────────────────────────────────────────────────

def kb_feedback_useful(day_number: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, полезен", callback_data=f"feedback:yes:{day_number}")
    kb.button(text="🤔 Не очень", callback_data=f"feedback:no:{day_number}")
    kb.adjust(2)
    return kb.as_markup()


def kb_feedback_skip(skip_data: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ Пропустить", callback_data=skip_data)
    return kb.as_markup()


def kb_feedback_recommend() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👍 Да, порекомендую", callback_data="feedback:recommend:yes")
    kb.button(text="👎 Пока нет", callback_data="feedback:recommend:no")
    kb.adjust(2)
    return kb.as_markup()


# ── Admin ─────────────────────────────────────────────────────────────────────

def kb_admin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="💳 Подписки", callback_data="admin:subs")
    kb.button(text="📋 Отзывы бета-теста", callback_data="admin:feedback")
    kb.adjust(1)
    return kb.as_markup()