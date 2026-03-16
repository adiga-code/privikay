from typing import Any

from database.models import DailyLog, User
from habits.registry import HABIT_REGISTRY, INDEX_HABITS


class AnalyticsService:
    """Pure computation: no DB access, only works with already-loaded objects."""

    # ── Day Index ─────────────────────────────────────────────────────────────

    def calculate_day_index(self, log: DailyLog, user: User) -> float:
        """
        Returns a normalised 0–10 score based on the habits the user selected
        that contribute to the index (steps, calories, sleep, stress, energy).
        """
        from habits.registry import BOOL_HABITS
        scoreable = [h for h in user.selected_habits if h in INDEX_HABITS]
        if not scoreable:
            return 0.0

        # Boolean habits (alcohol, smoking, no_sugar, meal_gap) max score = 1, others = 2
        max_score = sum(1 if h in BOOL_HABITS else 2 for h in scoreable)
        total = 0

        for key in scoreable:
            value = self._get_value(log, key)
            if value is None:
                continue
            result = HABIT_REGISTRY[key].evaluate(value, self._get_target(user, key))
            total += result.score

        return round((total / max_score) * 10, 1)

    def build_day_summary(self, log: DailyLog, user: User) -> str:
        """Build the post-check-in summary message."""
        index = self.calculate_day_index(log, user)
        good: list[str] = []
        attention: list[str] = []

        for key in user.selected_habits:
            if key not in INDEX_HABITS:
                continue
            value = self._get_value(log, key)
            if value is None:
                continue
            habit = HABIT_REGISTRY[key]
            result = habit.evaluate(value, self._get_target(user, key))
            if result.status == "done":
                good.append(f"— {habit.display_name}")
            elif result.status in ("almost", "failed"):
                attention.append(f"— {habit.display_name}")
            # "recorded" не учитываем (устаревший статус)

        lines = [f"🌟 *Индекс дня: {index} / 10*\n"]
        if good:
            lines.append("Сегодня хорошо сработали:")
            lines.extend(good)
        if attention:
            if good:
                lines.append("")
            lines.append("Стоит обратить внимание:")
            lines.extend(attention)

        return "\n".join(lines)

    # ── Streaks ───────────────────────────────────────────────────────────────

    def get_streaks(self, logs: list[DailyLog], user: User) -> dict[str, int]:
        """
        For each scoreable habit the user tracks, count how many consecutive
        days ending with the latest log were marked "done".
        """
        streaks: dict[str, int] = {}
        sorted_logs = sorted(logs, key=lambda l: l.date)

        for key in user.selected_habits:
            if key not in INDEX_HABITS:
                continue
            streak = 0
            for log in reversed(sorted_logs):
                value = self._get_value(log, key)
                if value is None:
                    break
                result = HABIT_REGISTRY[key].evaluate(value, self._get_target(user, key))
                if result.status == "done":
                    streak += 1
                else:
                    break
            streaks[key] = streak

        return streaks

    def format_streaks(self, streaks: dict[str, int]) -> str:
        lines = []
        for key, count in streaks.items():
            if count > 0:
                habit = HABIT_REGISTRY.get(key)
                name = habit.display_name if habit else key
                lines.append(f"{name} — {count} {self._days_word(count)}")
        return "\n".join(lines)

    # ── Insights ──────────────────────────────────────────────────────────────

    def get_insights(self, logs: list[DailyLog]) -> list[str]:
        """Return a list of data-driven observation strings (max 2)."""
        if len(logs) < 4:
            return []

        insights: list[str] = []

        # Insight: steps ↔ energy correlation
        steps_energy = [
            (l.steps, l.energy_level)
            for l in logs
            if l.steps is not None and l.energy_level is not None
        ]
        if len(steps_energy) >= 4:
            high = [e for s, e in steps_energy if s > 10_000]
            low = [e for s, e in steps_energy if s <= 5_000]
            if high and low:
                avg_high = sum(high) / len(high)
                avg_low = sum(low) / len(low)
                if avg_high > avg_low + 0.5:
                    insights.append(
                        "📊 В дни, когда вы проходите больше шагов, уровень энергии выше."
                    )

        # Insight: consistent good sleep
        sleep_logs = [l.sleep_hours for l in logs if l.sleep_hours is not None]
        if len(sleep_logs) >= 4:
            good = sum(1 for h in sleep_logs if 7 <= h <= 8)
            if good / len(sleep_logs) >= 0.7:
                insights.append(
                    "😴 Вы стабильно хорошо спите — это одна из ваших лучших привычек!"
                )

        return insights[:2]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_value(log: DailyLog, key: str) -> Any:
        return {
            "steps": log.steps,
            "calories": log.calories,
            "sleep": log.sleep_hours,
            "stress": log.stress_level,
            "energy": log.energy_level,
            "reading": log.reading_amount,
            "meal_gap": log.meal_gap,
            "alcohol": log.alcohol,
            "smoking": log.smoking,
            "no_sugar": log.no_sugar,
        }.get(key)

    @staticmethod
    def _get_target(user: User, key: str) -> Any:
        if key == "reading":
            unit = "минут" if user.reading_format == "minutes" else "страниц"
            return (user.reading_target or 30, unit)
        return {
            "steps": user.steps_target,
            "calories": user.calories_target,
            "meal_gap": user.meal_gap_target or 8,
        }.get(key)

    @staticmethod
    def _days_word(n: int) -> str:
        if 11 <= n % 100 <= 14:
            return "дней"
        r = n % 10
        if r == 1:
            return "день"
        if 2 <= r <= 4:
            return "дня"
        return "дней"
