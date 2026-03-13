from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.models import Base

engine = create_async_engine(settings.db_url, echo=False)
session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
