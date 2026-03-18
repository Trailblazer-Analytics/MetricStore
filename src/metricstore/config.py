"""Application configuration via pydantic-settings.

All settings are read from environment variables (or a .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from metricstore import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://metricstore:metricstore@localhost:5432/metricstore"
    )

    # Application
    app_name: str = "MetricStore"
    app_version: str = __version__
    debug: bool = False
    api_prefix: str = "/api/v1"


settings = Settings()
