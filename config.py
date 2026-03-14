from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: SecretStr
    bot_username: str = "Privykai_bot"
    db_url: str = "postgresql+asyncpg://bot:bot@localhost:5432/habits"
    academy_url: str = "https://example.com/academy"

    # ЮКасса: формат YUKASSA_TOKEN = "shopId:MODE:secretKey"
    yukassa_token: str = ""

    # Subscription prices in kopecks (RUB × 100)
    price_monthly: int = 24900   # 249 RUB
    price_yearly: int = 179000   # 1790 RUB

    # Trial period in days
    trial_days: int = 15

    # Comma-separated admin Telegram user IDs, e.g. "123456789,987654321"
    admin_ids: str = ""

    @property
    def admin_id_list(self) -> list[int]:
        if not self.admin_ids.strip():
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def yukassa_shop_id(self) -> str:
        """Parse shopId from YUKASSA_TOKEN (format: shopId:MODE:secretKey)."""
        parts = self.yukassa_token.split(":")
        return parts[0] if parts else ""

    @property
    def yukassa_secret_key(self) -> str:
        """Parse secretKey from YUKASSA_TOKEN (format: shopId:MODE:secretKey)."""
        parts = self.yukassa_token.split(":", 2)
        return parts[2] if len(parts) >= 3 else self.yukassa_token

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
