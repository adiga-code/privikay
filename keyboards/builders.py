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
    timezones = [
        (2,  "UTC+2 (Калининград)"),
        (3,  "UTC+3 (Москва, СПб)"),
        (4,  "UTC+4 (Самара, Баку)"),
        (5,  "UTC+5 (Екатеринбург)"),
        (6,  "UTC+6 (Омск)"),
        (7,  "UTC+7 (Красноярск, Новосибирск)"),
        (8,  "UTC+8 (Иркутск, Улан-Удэ)"),
        (9,  "UTC+9 (Якутск)"),
        (10, "UTC+10 (Владивосток)"),
        (11, "UTC+11 (Магадан)"),
        (12, "UTC+12 (Камчатка)"),
        (0,  "UTC+0 (Лондон)"),
        (1,  "UTC+1 (Берлин, Варшава)"),
    ]
    for off, label in timezones:
        kb.button(text=label, callback_data=f"tz:{off}")
    kb.adjust(1)
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
    """Для вредных привычек: Да=плохо(❌), Нет=хорошо(✅)."""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Да", callback_data=yes_data)
    kb.button(text="✅ Нет", callback_data=no_data)
    kb.adjust(2)
    return kb.as_markup()


def kb_yes_no_positive(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """Для полезных привычек: Да=хорошо(✅), Нет=плохо(❌)."""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=yes_data)
    kb.button(text="❌ Нет", callback_data=no_data)
    kb.adjust(2)
    return kb.as_markup()


# ── Check-in edit ─────────────────────────────────────────────────────────────

def kb_checkin_edit() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить ответы", callback_data="checkin:edit_all")
    kb.button(text="➕ Добавить пропущенное", callback_data="checkin:edit_missing")
    kb.button(text="✅ Оставить как есть", callback_data="checkin:edit_keep")
    kb.adjust(1)
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


# ── Open feedback (free-text) ─────────────────────────────────────────────────

def kb_feedback_entry() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Оставить отзыв", callback_data="open_feedback:start")
    kb.button(text="⚙️ Изменить настройки", callback_data="settings:open")
    kb.adjust(1)
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


# ── Nutrition onboarding ──────────────────────────────────────────────────────

def kb_nutrition_mode() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Считать калории", callback_data="nutrition:mode:count")
    kb.button(text="📖 Хочу разобраться как считать", callback_data="nutrition:mode:learn")
    kb.button(text="🥗 Не хочу считать калории", callback_data="nutrition:mode:simplified")
    kb.adjust(1)
    return kb.as_markup()


def kb_nutrition_method() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Ввести свою цель", callback_data="nutrition:method:manual")
    kb.button(text="🧮 Помочь рассчитать", callback_data="nutrition:method:calculate")
    kb.adjust(1)
    return kb.as_markup()


def kb_nutrition_gender() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👨 Мужской", callback_data="nutrition:gender:m")
    kb.button(text="👩 Женский", callback_data="nutrition:gender:f")
    kb.adjust(2)
    return kb.as_markup()


def kb_nutrition_activity() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🪑 Сидячий образ жизни", callback_data="nutrition:activity:sedentary")
    kb.button(text="🚶 Лёгкая активность", callback_data="nutrition:activity:light")
    kb.button(text="🏃 Средняя активность", callback_data="nutrition:activity:moderate")
    kb.button(text="💪 Высокая активность", callback_data="nutrition:activity:high")
    kb.adjust(1)
    return kb.as_markup()


def kb_nutrition_goal_type() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬇️ Похудение", callback_data="nutrition:goal:lose")
    kb.button(text="⚖️ Поддержание веса", callback_data="nutrition:goal:maintain")
    kb.button(text="💪 Набор мышечной массы", callback_data="nutrition:goal:gain")
    kb.adjust(1)
    return kb.as_markup()


def kb_nutrition_confirm(calories: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Использовать {calories} ккал", callback_data=f"nutrition:confirm:{calories}")
    kb.button(text="✏️ Изменить вручную", callback_data="nutrition:confirm:manual")
    kb.adjust(1)
    return kb.as_markup()


def kb_nutrition_guide() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ Продолжить", callback_data="nutrition:guide:continue")
    kb.button(text="📄 Скачать полный гайд", callback_data="nutrition:guide:pdf")
    kb.adjust(1)
    return kb.as_markup()


# ── Nutrition checkin (simplified / learn mode) ───────────────────────────────

def kb_nutrition_checkin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ По плану", callback_data="ci_nutrition:on_plan")
    kb.button(text="🟡 Частично по плану", callback_data="ci_nutrition:partly")
    kb.button(text="❌ Не по плану", callback_data="ci_nutrition:off_plan")
    kb.adjust(1)
    return kb.as_markup()


# ── Referral ──────────────────────────────────────────────────────────────────

def kb_invite_friends(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Поделиться ссылкой", switch_inline_query=link)
    kb.button(text="📋 Скопировать ссылку", callback_data=f"referral:copy:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def kb_support_friends() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Начать с друзьями", callback_data="group:start")
    kb.button(text="⏭ Позже", callback_data="group:later")
    kb.adjust(1)
    return kb.as_markup()


# ── Support groups ────────────────────────────────────────────────────────────

def kb_group_choice() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать группу", callback_data="group:create")
    kb.button(text="🔑 Ввести код группы", callback_data="group:join")
    kb.adjust(1)
    return kb.as_markup()


def kb_group_share(code: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Скопировать код", callback_data=f"group:copy:{code}")
    kb.button(text="📤 Поделиться кодом", switch_inline_query=f"Присоединяйся к моей группе поддержки! Код: {code}")
    kb.adjust(1)
    return kb.as_markup()


# ── Admin broadcast ───────────────────────────────────────────────────────────

def kb_broadcast_filters() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Все пользователи", callback_data="broadcast:filter:all")
    kb.button(text="🆓 На триале", callback_data="broadcast:filter:trial")
    kb.button(text="💳 Платная подписка", callback_data="broadcast:filter:paid")
    kb.button(text="🎯 По цели", callback_data="broadcast:filter:goal")
    kb.button(text="✅ Активные (7 дней)", callback_data="broadcast:filter:active")
    kb.adjust(1)
    return kb.as_markup()


def kb_broadcast_goals() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🕐 Наладить режим", callback_data="broadcast:goal:routine")
    kb.button(text="🏃 Больше двигаться", callback_data="broadcast:goal:move_more")
    kb.button(text="⚖️ Похудеть", callback_data="broadcast:goal:lose_weight")
    kb.button(text="🧘 Снизить стресс", callback_data="broadcast:goal:reduce_stress")
    kb.button(text="🚫 Избавиться от привычек", callback_data="broadcast:goal:quit_bad_habits")
    kb.adjust(1)
    return kb.as_markup()


def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="broadcast:send")
    kb.button(text="❌ Отмена", callback_data="broadcast:cancel")
    kb.adjust(2)
    return kb.as_markup()


# ── Admin ─────────────────────────────────────────────────────────────────────

def kb_admin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="💳 Подписки", callback_data="admin:subs")
    kb.button(text="📋 Отзывы бета-теста", callback_data="admin:feedback")
    kb.button(text="🔗 Рефералы", callback_data="admin:referrals")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.adjust(1)
    return kb.as_markup()