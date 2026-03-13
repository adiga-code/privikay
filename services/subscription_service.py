from datetime import datetime, timedelta

from database.models import SubscriptionPlan, User


TRIAL_DAYS = 15


class SubscriptionService:
    """Pure subscription business logic — no DB access."""

    def is_active(self, user: User) -> bool:
        return self.is_trial(user) or self.is_subscribed(user)

    def is_trial(self, user: User) -> bool:
        return (datetime.utcnow() - user.registered_at).days < TRIAL_DAYS

    def is_subscribed(self, user: User) -> bool:
        return (
            user.subscription_expires_at is not None
            and user.subscription_expires_at > datetime.utcnow()
        )

    def trial_days_left(self, user: User) -> int:
        elapsed = (datetime.utcnow() - user.registered_at).days
        return max(0, TRIAL_DAYS - elapsed)

    def subscription_days_left(self, user: User) -> int:
        if not self.is_subscribed(user):
            return 0
        return (user.subscription_expires_at - datetime.utcnow()).days

    def activate(self, user: User, plan: SubscriptionPlan) -> datetime:
        """Return new expiry datetime for the given plan."""
        base = max(datetime.utcnow(), user.subscription_expires_at or datetime.utcnow())
        delta = timedelta(days=30) if plan == SubscriptionPlan.MONTHLY else timedelta(days=365)
        return base + delta