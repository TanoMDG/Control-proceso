from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    internal_networks: str = "127.0.0.1/32,::1/128"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
