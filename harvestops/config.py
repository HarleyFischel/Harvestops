from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    demo_mode: bool = True
    storage_mode: str = "demo"
    secret_key: str = "local-only-change-me"
    display_timezone: str = "America/New_York"
    identity_mode: str = "demo"
    sql_server: str = ""
    sql_database: str = "HarvestOps"
    sql_user: str = ""
    sql_password: str = ""
    sql_encrypt: bool = True
    sql_trust_server_certificate: bool = False
    sql_connection_timeout: int = 5
    session_redis_url: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    entra_tenant_id: str = ""
    entra_redirect_uri: str = "http://localhost:8050/auth/callback"
    claude_api_key: str = ""
    claude_model: str = "claude-3-5-haiku-latest"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_for_runtime(self) -> list[str]:
        errors: list[str] = []
        if self.app_env == "production" and self.demo_mode:
            errors.append("DEMO_MODE must be false in production")
        if self.app_env == "production" and self.identity_mode != "entra":
            errors.append("IDENTITY_MODE must be entra in production")
        if self.identity_mode == "entra":
            for name in ("entra_client_id", "entra_client_secret", "entra_tenant_id"):
                if not getattr(self, name):
                    errors.append(f"{name.upper()} is required for Entra mode")
        if self.storage_mode == "sqlserver":
            for name in ("sql_server", "sql_database", "sql_user", "sql_password"):
                if not getattr(self, name):
                    errors.append(f"{name.upper()} is required for SQL Server mode")
        if self.app_env == "production" and not self.session_redis_url:
            errors.append("SESSION_REDIS_URL is required for production server-side sessions")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
