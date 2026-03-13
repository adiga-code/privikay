from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HabitResult:
    """Immutable result of evaluating a single habit entry."""

    status: str   # "done" | "almost" | "failed" | "recorded"
    score: int    # contribution to day index: 0–2
    label: str    # human-readable status with emoji


class Habit(ABC):
    """
    Abstract base for all habit types.
    Subclass and implement evaluate(), validate(), question().
    """

    key: str           # unique machine identifier, e.g. "steps"
    display_name: str  # shown in UI, e.g. "Шаги"
    emoji: str         # single emoji for compact display

    @abstractmethod
    def validate(self, raw: str) -> Any:
        """
        Parse and validate raw string input from the user.
        Raises ValueError with a user-friendly message on invalid input.
        """

    @abstractmethod
    def evaluate(self, value: Any, target: Any = None) -> HabitResult:
        """Return HabitResult for the given recorded value."""

    @abstractmethod
    def question(self, target: Any = None) -> str:
        """Return the check-in question to send the user."""
