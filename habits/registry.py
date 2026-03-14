from habits.base import Habit
from habits.types import (
    AlcoholHabit, CaloriesHabit, EnergyHabit,
    MealGapHabit, NoSugarHabit, ReadingHabit,
    SleepHabit, SmokingHabit, StepsHabit, StressHabit,
)

HABIT_REGISTRY: dict[str, Habit] = {
    cls.key: cls()
    for cls in (
        StepsHabit, CaloriesHabit, SleepHabit, StressHabit,
        EnergyHabit, AlcoholHabit, SmokingHabit, NoSugarHabit,
        ReadingHabit, MealGapHabit,
    )
}

INDEX_HABITS: frozenset[str] = frozenset({
    "steps", "calories", "sleep", "stress", "energy", "reading", "meal_gap",
})
SCALE_HABITS: frozenset[str] = frozenset({"stress", "energy"})
BOOL_HABITS: frozenset[str] = frozenset({"alcohol", "smoking", "no_sugar", "meal_gap"})
TEXT_HABITS: frozenset[str] = frozenset({"steps", "calories", "sleep", "reading"})

# Ordered list for the selection screen (weight appended dynamically if needed)
SELECTABLE_HABIT_KEYS: list[str] = [
    "steps", "calories", "sleep", "stress", "energy",
    "alcohol", "smoking", "no_sugar", "reading", "meal_gap",
]