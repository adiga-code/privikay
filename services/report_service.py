from database.models import DailyLog, User, WeightLog
from heroes.data import get_hero
from services.analytics_service import AnalyticsService


class ReportService:
    def __init__(self, analytics: AnalyticsService) -> None:
        self.analytics = analytics

    def build_weekly_report(
        self, user: User, logs: list[DailyLog], weight_logs: list[WeightLog]
    ) -> str:
        hero = get_hero(user.hero_key)
        if not logs:
            return f"{hero.phrase('report')}\n\nЗа эту неделю данных пока нет. Продолжайте вести чек-ины! 💪"

        selected = user.selected_habits
        lines = [hero.phrase("report"), f"\n📊 *Отчёт за неделю, {user.name}!*\n"]

        if "steps" in selected:
            total = sum(l.steps for l in logs if l.steps is not None)
            lines.append(f"👟 *Шаги:* {total:,} за неделю")

        if "calories" in selected and user.calories_target:
            on_target = sum(
                1 for l in logs
                if l.calories and abs(l.calories - user.calories_target) / user.calories_target <= 0.10
            )
            lines.append(f"🍎 *Питание:* цель выполнена {on_target} из {len(logs)} дней")

        if "sleep" in selected:
            vals = [l.sleep_hours for l in logs if l.sleep_hours is not None]
            if vals:
                lines.append(f"😴 *Сон:* в среднем {sum(vals) / len(vals):.1f} ч")

        if "stress" in selected:
            vals = [l.stress_level for l in logs if l.stress_level is not None]
            if vals:
                lines.append(f"🧘 *Стресс:* средний уровень {sum(vals) / len(vals):.1f} / 5")

        if "energy" in selected:
            vals = [l.energy_level for l in logs if l.energy_level is not None]
            if vals:
                lines.append(f"⚡ *Энергия:* средний уровень {sum(vals) / len(vals):.1f} / 5")

        if "alcohol" in selected:
            clean = sum(1 for l in logs if l.alcohol is not None and not l.alcohol)
            lines.append(f"🍷 *Алкоголь:* {clean} дней без алкоголя")

        if "smoking" in selected:
            clean = sum(1 for l in logs if l.smoking is not None and not l.smoking)
            lines.append(f"🚬 *Курение:* {clean} дней без курения")

        if "no_sugar" in selected:
            clean = sum(1 for l in logs if l.no_sugar is not None and not l.no_sugar)
            lines.append(f"🍬 *Без сахара:* {clean} дней без сахара")

        if weight_logs and len(weight_logs) >= 2:
            latest, prev, first = weight_logs[-1].weight, weight_logs[-2].weight, weight_logs[0].weight
            lines += [
                f"\n⚖️ *Вес:*",
                f"  За неделю: {_sign(latest - prev)}{latest - prev:.1f} кг",
                f"  С начала: {_sign(latest - first)}{latest - first:.1f} кг",
            ]

        indices = [l.day_index for l in logs if l.day_index is not None]
        if indices:
            avg = sum(indices) / len(indices)
            lines.append(f"\n🌟 *Средний индекс недели:* {avg:.1f} / 10")

        streaks = self.analytics.get_streaks(logs, user)
        streak_text = self.analytics.format_streaks(streaks)
        if streak_text:
            lines.append(f"\n🔥 *Серии:*\n{streak_text}")

        return "\n".join(lines)

    def build_progress_card(self, user: User, logs: list[DailyLog]) -> str:
        """7-day shareable text card with hero personality."""
        hero = get_hero(user.hero_key)
        lines = [
            f"╔══════════════════╗",
            f"  {hero.emoji}  МОЯ НЕДЕЛЯ ПРИВЫЧЕК",
            f"╚══════════════════╝\n",
        ]

        if "steps" in user.selected_habits:
            total = sum(l.steps for l in logs if l.steps is not None)
            lines.append(f"👟  Шаги          {total:>10,}")

        if "sleep" in user.selected_habits:
            vals = [l.sleep_hours for l in logs if l.sleep_hours is not None]
            if vals:
                lines.append(f"😴  Сон       {sum(vals) / len(vals):>10.1f} ч")

        if "alcohol" in user.selected_habits:
            clean = sum(1 for l in logs if l.alcohol is not None and not l.alcohol)
            lines.append(f"🍷  Алкоголь       {clean:>7} дней без")

        if "no_sugar" in user.selected_habits:
            clean = sum(1 for l in logs if l.no_sugar is not None and not l.no_sugar)
            lines.append(f"🍬  Без сахара     {clean:>7} дней")

        indices = [l.day_index for l in logs if l.day_index is not None]
        if indices:
            avg = sum(indices) / len(indices)
            lines.append(f"\n🌟  Индекс недели   {avg:>7.1f} / 10")

        lines += [
            f"\n{hero.phrase('done')}",
            f"\n_Отслеживаю привычки в Habit Tracker Bot_",
        ]
        return "\n".join(lines)


def _sign(v: float) -> str:
    return "+" if v > 0 else ""