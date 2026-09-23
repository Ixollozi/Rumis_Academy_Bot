from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./rumis_bot.db",
        alias="DATABASE_URL",
    )
    admin_ids: str = Field(default="", alias="ADMIN_IDS")

    center_name: str = Field(default="Rumis Academy", alias="CENTER_NAME")
    center_address: str = Field(default="", alias="CENTER_ADDRESS")
    center_phone: str = Field(default="", alias="CENTER_PHONE")
    admin_telegram: str = Field(default="", alias="ADMIN_TELEGRAM")
    speaking_contact: str = Field(default="", alias="SPEAKING_CONTACT")
    mock_channel: str = Field(default="@rumis_academy_mock", alias="MOCK_CHANNEL")
    payment_details: str = Field(default="", alias="PAYMENT_DETAILS")
    location_lat: float | None = Field(default=None, alias="LOCATION_LAT")
    location_lon: float | None = Field(default=None, alias="LOCATION_LON")
    maps_url: str = Field(default="", alias="MAPS_URL")

    default_price_own: int = Field(default=75_000, alias="DEFAULT_PRICE_OWN")
    default_price_new: int = Field(default=150_000, alias="DEFAULT_PRICE_NEW")
    default_date_limit: int = Field(default=10, alias="DEFAULT_DATE_LIMIT")
    timezone: str = Field(default="Asia/Tashkent", alias="TIMEZONE")

    google_sheets_id: str = Field(default="", alias="GOOGLE_SHEETS_ID")
    google_credentials_json: str = Field(default="", alias="GOOGLE_CREDENTIALS_JSON")
    bot_username: str = Field(default="@CDI_Rumis_Bot", alias="BOT_USERNAME")

    @field_validator("location_lat", "location_lon", mode="before")
    @classmethod
    def empty_float_to_none(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return v

    @field_validator("payment_details", "speaking_contact", mode="before")
    @classmethod
    def unescape_newlines(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.replace("\\n", "\n").strip()
        return v

    @property
    def admin_id_list(self) -> list[int]:
        from app.services import admin_access

        cached = admin_access.cached_admin_ids()
        if cached:
            return cached
        # Before first sync (or empty DB): fall back to .env
        if not self.admin_ids.strip():
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def env_owner_ids(self) -> list[int]:
        if not self.admin_ids.strip():
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    def is_admin(self, user_id: int) -> bool:
        from app.services import admin_access

        if admin_access.cached_admin_ids():
            return admin_access.is_admin(user_id)
        return user_id in self.env_owner_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
