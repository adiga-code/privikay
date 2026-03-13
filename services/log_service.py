from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DailyLog, WeightLog


class LogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Daily logs ────────────────────────────────────────────────────────────

    async def get_today_log(self, user_id: int) -> DailyLog | None:
        result = await self.session.execute(
            select(DailyLog).where(
                DailyLog.user_id == user_id,
                DailyLog.date == date.today(),
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_today_log(self, user_id: int) -> DailyLog:
        log = await self.get_today_log(user_id)
        if log is None:
            log = DailyLog(user_id=user_id, date=date.today())
            self.session.add(log)
            await self.session.commit()
            await self.session.refresh(log)
        return log

    async def update_log(self, log: DailyLog, **kwargs) -> DailyLog:
        for key, value in kwargs.items():
            setattr(log, key, value)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_logs_between(
        self, user_id: int, from_date: date, to_date: date
    ) -> list[DailyLog]:
        result = await self.session.execute(
            select(DailyLog)
            .where(
                DailyLog.user_id == user_id,
                DailyLog.date >= from_date,
                DailyLog.date <= to_date,
            )
            .order_by(DailyLog.date)
        )
        return list(result.scalars().all())

    async def get_all_logs(self, user_id: int) -> list[DailyLog]:
        result = await self.session.execute(
            select(DailyLog)
            .where(DailyLog.user_id == user_id)
            .order_by(DailyLog.date)
        )
        return list(result.scalars().all())

    # ── Weight logs ───────────────────────────────────────────────────────────

    async def add_weight(self, user_id: int, weight: float) -> WeightLog:
        log = WeightLog(user_id=user_id, date=date.today(), weight=weight)
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_weight_logs(self, user_id: int) -> list[WeightLog]:
        result = await self.session.execute(
            select(WeightLog)
            .where(WeightLog.user_id == user_id)
            .order_by(WeightLog.date)
        )
        return list(result.scalars().all())
