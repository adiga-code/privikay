from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from database.models import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_or_raise(self, user_id: int) -> User:
        user = await self.get(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found.")
        return user

    async def create(self, user_id: int, name: str) -> User:
        user = User(id=user_id, name=name)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        if "selected_habits" in kwargs:
            attributes.flag_modified(user, "selected_habits")
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_all_active(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.onboarding_done.is_(True))
        )
        return list(result.scalars().all())

    async def get_by_checkin_time(self, checkin_time: str) -> list[User]:
        result = await self.session.execute(
            select(User).where(
                User.onboarding_done.is_(True),
                User.checkin_time == checkin_time,
            )
        )
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        from datetime import datetime
        from sqlalchemy import func, and_
        result = await self.session.execute(select(User))
        all_users = list(result.scalars().all())
        total = len(all_users)
        onboarded = sum(1 for u in all_users if u.onboarding_done)
        subscribed = sum(
            1 for u in all_users
            if u.subscription_expires_at and u.subscription_expires_at > datetime.utcnow()
        )
        return {"total": total, "onboarded": onboarded, "subscribed": subscribed}