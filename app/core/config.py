from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AsanBar"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production-at-least-32-characters"

    DATABASE_URL: str = "postgresql+asyncpg://asanbar:asanbar123@localhost:5432/asanbar_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    RATE_LIMIT_COMPANY: int = 100
    RATE_LIMIT_DRIVER: int = 60
    RATE_LIMIT_DEFAULT: int = 30

    DRIVER_SEARCH_RADIUS_KM: float = 5.0
    DRIVER_RESPONSE_TIMEOUT_SEC: int = 30
    MAX_ASSIGNMENT_ATTEMPTS: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
