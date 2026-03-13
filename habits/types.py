from habits.base import Habit, HabitResult


class StepsHabit(Habit):
    key = "steps"
    display_name = "Шаги"
    emoji = "👟"

    def validate(self, raw: str) -> int:
        value = int(raw.strip())
        if not (0 <= value <= 100_000):
            raise ValueError("Введите число от 0 до 100 000.")
        return value

    def evaluate(self, value: int, target: int = 15_000) -> HabitResult:
        ratio = value / target
        if ratio >= 1.0:
            return HabitResult("done", 2, "✅ Выполнено")
        if ratio >= 0.8:
            return HabitResult("almost", 1, "🟡 Почти выполнено")
        return HabitResult("failed", 0, "❌ Не выполнено")

    def question(self, target: int = 15_000) -> str:
        return f"👟 Сколько шагов вы прошли сегодня?\n_Цель: {target:,} шагов_"


class CaloriesHabit(Habit):
    key = "calories"
    display_name = "Питание"
    emoji = "🍎"

    def validate(self, raw: str) -> int:
        value = int(raw.strip())
        if not (0 <= value <= 15_000):
            raise ValueError("Введите число от 0 до 15 000.")
        return value

    def evaluate(self, value: int, target: int = 2000) -> HabitResult:
        diff = abs(value - target) / target
        if diff <= 0.10:
            return HabitResult("done", 2, "✅ В пределах цели")
        if diff <= 0.25:
            return HabitResult("almost", 1, "🟡 Небольшое отклонение")
        return HabitResult("failed", 0, "❌ Сильное отклонение")

    def question(self, target: int = 2000) -> str:
        return f"🍎 Сколько калорий вы сегодня съели?\n_Цель: {target:,} ккал_"


class SleepHabit(Habit):
    key = "sleep"
    display_name = "Сон"
    emoji = "😴"

    def validate(self, raw: str) -> float:
        value = float(raw.strip().replace(",", "."))
        if not (0 <= value <= 24):
            raise ValueError("Введите число от 0 до 24.")
        return value

    def evaluate(self, value: float, target: None = None) -> HabitResult:
        if 7 <= value <= 8:
            return HabitResult("done", 2, "✅ Отлично (7–8 ч)")
        if 6 <= value < 7:
            return HabitResult("almost", 1, "🟡 Почти (6–7 ч)")
        return HabitResult("failed", 0, "❌ Мало сна")

    def question(self, target: None = None) -> str:
        return "😴 Сколько часов вы спали?\n_Цель: 7–8 часов_"


class StressHabit(Habit):
    key = "stress"
    display_name = "Стресс"
    emoji = "🧘"

    _LABELS = {1: "Спокойно", 2: "Немного напряжён", 3: "Средний", 4: "Высокий", 5: "Очень высокий"}

    def validate(self, raw: str) -> int:
        value = int(raw.strip())
        if value not in range(1, 6):
            raise ValueError("Введите число от 1 до 5.")
        return value

    def evaluate(self, value: int, target: None = None) -> HabitResult:
        label = self._LABELS.get(value, str(value))
        if value <= 2:
            return HabitResult("done", 2, f"✅ {label}")
        if value == 3:
            return HabitResult("almost", 1, f"🟡 {label}")
        return HabitResult("failed", 0, f"❌ {label}")

    def question(self, target: None = None) -> str:
        return (
            "🧘 Какой уровень стресса?\n\n"
            "1 — спокойно\n2 — немного напряжён\n3 — средний\n4 — высокий\n5 — очень высокий"
        )


class EnergyHabit(Habit):
    key = "energy"
    display_name = "Энергия"
    emoji = "⚡"

    _LABELS = {1: "Нет сил", 2: "Низкая", 3: "Нормальная", 4: "Высокая", 5: "Очень высокая"}

    def validate(self, raw: str) -> int:
        value = int(raw.strip())
        if value not in range(1, 6):
            raise ValueError("Введите число от 1 до 5.")
        return value

    def evaluate(self, value: int, target: None = None) -> HabitResult:
        label = self._LABELS.get(value, str(value))
        if value >= 4:
            return HabitResult("done", 2, f"✅ {label}")
        if value == 3:
            return HabitResult("almost", 1, f"🟡 {label}")
        return HabitResult("failed", 0, f"❌ {label}")

    def question(self, target: None = None) -> str:
        return (
            "⚡ Какой уровень энергии?\n\n"
            "1 — нет сил\n2 — низкая\n3 — нормальная\n4 — высокая\n5 — очень высокая"
        )


class AlcoholHabit(Habit):
    key = "alcohol"
    display_name = "Алкоголь"
    emoji = "🍷"

    def validate(self, raw: str) -> bool:
        if raw in ("0", "no", "нет"):
            return False
        if raw in ("1", "yes", "да"):
            return True
        raise ValueError("Используйте кнопки Да / Нет.")

    def evaluate(self, value: bool, target: None = None) -> HabitResult:
        if not value:
            return HabitResult("done", 0, "✅ Без алкоголя")
        return HabitResult("recorded", 0, "📝 Был алкоголь")

    def question(self, target: None = None) -> str:
        return "🍷 Сегодня был алкоголь?"


class SmokingHabit(Habit):
    key = "smoking"
    display_name = "Курение"
    emoji = "🚬"

    def validate(self, raw: str) -> bool:
        if raw in ("0", "no", "нет"):
            return False
        if raw in ("1", "yes", "да"):
            return True
        raise ValueError("Используйте кнопки Да / Нет.")

    def evaluate(self, value: bool, target: None = None) -> HabitResult:
        if not value:
            return HabitResult("done", 0, "✅ Не курил")
        return HabitResult("recorded", 0, "📝 Было курение")

    def question(self, target: None = None) -> str:
        return "🚬 Сегодня курил?"


class NoSugarHabit(Habit):
    key = "no_sugar"
    display_name = "Без сахара"
    emoji = "🍬"

    def validate(self, raw: str) -> bool:
        if raw in ("0", "no", "нет"):
            return False
        if raw in ("1", "yes", "да"):
            return True
        raise ValueError("Используйте кнопки Да / Нет.")

    def evaluate(self, value: bool, target: None = None) -> HabitResult:
        if not value:
            return HabitResult("done", 0, "✅ День без сахара!")
        return HabitResult("recorded", 0, "📝 Был сахар")

    def question(self, target: None = None) -> str:
        return "🍬 Сегодня был сахар?"