from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeoMarket B2C"
    app_env: str = "production"
    database_url: str = "postgresql+psycopg://neomarket:neomarket_pass@localhost:5432/neomarket_tea_b2c"
    auto_seed: bool = True
    demo_user_id: str = "11111111-1111-1111-1111-111111111111"
    demo_session_id: str = "sess-demo-001"
    b2b_base_url: str = ""
    b2b_service_key: str = ""
    b2b_auth_token: str = ""
    b2b_timeout_seconds: float = 3.0
    cors_origins: str = "*"
    trusted_hosts: str = "127.0.0.1,localhost,109.71.246.85"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
