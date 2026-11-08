"""Runtime settings from environment variables (.env). Secrets never live in the repo."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # env_ignore_empty: "DATABASE_URL=" in a copied .env.example means "use the default", not an empty URL
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_ignore_empty=True)

    app_env: str = "dev"                          # dev | prod
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'finadvisor.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # auth: "supabase" verifies Supabase-issued JWTs; "dev" issues local tokens (refused when app_env=prod)
    auth_mode: str = "dev"
    supabase_url: str = ""
    supabase_service_key: str = ""                # server-only; needed to delete a Supabase Auth user
    supabase_anon_key: str = ""                   # public key; enough to verify sessions and sign out
    supabase_jwt_secret: str = ""                 # legacy HS256 projects; newer projects use JWKS
    dev_auth_secret: str = "dev-only-signing-key-not-a-secret-0000"

    ollama_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "website"                   # key in configs/models.yaml
    retrieval: str = "chroma"                     # chroma | keyword
    news: str = "rss"                             # rss (ET Markets + Moneycontrol, FinBERT mood) | off
    serve_web: bool = False                       # also serve the built website (web/dist) from the API, one address

    def check(self) -> None:
        if self.app_env == "prod" and self.auth_mode == "dev":
            raise RuntimeError("AUTH_MODE=dev is not allowed when APP_ENV=prod")
        if self.auth_mode == "supabase" and not self.supabase_url:
            raise RuntimeError("AUTH_MODE=supabase needs SUPABASE_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.check()
    return s
