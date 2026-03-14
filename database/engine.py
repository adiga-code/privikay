from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.models import Base

engine = create_async_engine(settings.db_url, echo=False)
session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Columns that might be missing from an older schema.
# Each entry: (table, column, definition)
_MIGRATIONS = [
    ("users", "hero_key",            "VARCHAR(20) NOT NULL DEFAULT 'capybara'"),
    ("users", "academy_offered",     "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("users", "last_feedback_sent",  "DATE"),
    ("users", "city",                "VARCHAR(100)"),
    ("users", "district",            "VARCHAR(100)"),
    ("users", "reading_format",      "VARCHAR(10)"),
    ("users", "reading_target",      "INTEGER"),
    ("users", "meal_gap_target",     "SMALLINT"),
    ("daily_logs", "reading_amount", "INTEGER"),
    ("daily_logs", "meal_gap",       "BOOLEAN"),
]


async def migrate_db() -> None:
    """Add missing columns to existing tables. Safe to run on every startup."""
    async with engine.begin() as conn:
        for table, column, definition in _MIGRATIONS:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            )


async def create_db() -> None:
    """Create all tables if they don't exist, then apply column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_db()
