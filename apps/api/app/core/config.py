from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    app_env: str = "development"
    api_cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://reconmate:change-me-for-local-development@localhost:5432/reconmate"
    ai_provider: str = "mock"
    ai_model: str | None = None
    simulation_tick_interval_seconds: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
