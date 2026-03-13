import enum
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, Float, Integer, JSON, SmallInteger, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserGoal(str, enum.Enum):
    ROUTINE = "routine"
    MOVE_MORE = "move_more"
    LOSE_WEIGHT = "lose_weight"
    REDUCE_STRESS = "reduce_stress"
    QUIT_BAD_HABITS = "quit_bad_habits"


class WeightGoal(str, enum.Enum):
    NONE = "none"
    LOSE = "lose"
    GAIN = "gain"


class SubscriptionPlan(str, enum.Enum):
    NONE = "none"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Goals
    goal: Mapped[UserGoal | None] = mapped_column(Enum(UserGoal), nullable=True)
    weight_goal: Mapped[WeightGoal] = mapped_column(Enum(WeightGoal), default=WeightGoal.NONE)

    # Hero
    hero_key: Mapped[str] = mapped_column(String(20), default="capybara")

    # Habits
    selected_habits: Mapped[list] = mapped_column(JSON, default=list)
    steps_target: Mapped[int] = mapped_column(Integer, default=15000)
    calories_target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timezone & schedule (stored as UTC strings "HH:MM")
    timezone_offset: Mapped[int] = mapped_column(SmallInteger, default=3)  # UTC+3 default
    checkin_time: Mapped[str] = mapped_column(String(5), default="18:00")  # UTC
    sleep_target_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # UTC

    # Subscription
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan), default=SubscriptionPlan.NONE
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Flags
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    academy_offered: Mapped[bool] = mapped_column(Boolean, default=False)

    # Scheduler tracking
    last_weekly_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_weight_check: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_insight_sent: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_feedback_sent: Mapped[date | None] = mapped_column(Date, nullable=True)


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alcohol: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    smoking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    no_sugar: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    day_index: Mapped[float | None] = mapped_column(Float, nullable=True)


class FeedbackLog(Base):
    __tablename__ = "feedback_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_name: Mapped[str] = mapped_column(String(100), default="")
    day_number: Mapped[int] = mapped_column(SmallInteger)  # 5, 10, or 15
    is_useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    likes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    dislikes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    would_recommend: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    date: Mapped[date] = mapped_column(Date)
    weight: Mapped[float] = mapped_column(Float)