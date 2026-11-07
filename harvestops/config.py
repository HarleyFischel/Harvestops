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
    sql_auth_mode: str = "sql_login"
    sql_user: str = ""
    sql_password: str = ""
    sql_encrypt: bool = True
    sql_trust_server_certificate: bool = False
    sql_connection_timeout: int = 5
    azure_client_id: str = ""
    session_redis_url: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    entra_tenant_id: str = ""
    entra_redirect_uri: str = "http://localhost:8050/auth/callback"
    claude_api_key: str = ""
    claude_model: str = "claude-3-5-haiku-latest"
    evidence_snapshot_path: str = "evidence/snapshot.json"
    github_repository: str = "HarleyFischel/Harvestops"
    github_api_url: str = "https://api.github.com"
    github_evidence_token: str = ""
    github_evidence_timeout: float = 5.0
    evidence_cache_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_for_runtime(self) -> list[str]:
        errors: list[str] = []
        if self.app_env == "production" and (
            self.secret_key == "local-only-change-me" or len(self.secret_key) < 32
        ):
            errors.append(
                "SECRET_KEY must be a generated value of at least 32 characters in production"
            )
        if self.app_env == "production" and self.demo_mode:
            errors.append("DEMO_MODE must be false in production")
        if self.app_env == "production" and self.identity_mode != "entra":
            errors.append("IDENTITY_MODE must be entra in production")
        if self.app_env == "production" and self.storage_mode != "sqlserver":
            errors.append("STORAGE_MODE must be sqlserver in production")
        if self.app_env == "production" and not self.sql_encrypt:
            errors.append("SQL_ENCRYPT must be true in production")
        if self.app_env == "production" and self.sql_trust_server_certificate:
            errors.append("SQL_TRUST_SERVER_CERTIFICATE must be false in production")
        if self.identity_mode == "entra":
            for name in ("entra_client_id", "entra_client_secret", "entra_tenant_id"):
                if not getattr(self, name):
                    errors.append(f"{name.upper()} is required for Entra mode")
        if self.storage_mode == "sqlserver":
            for name in ("sql_server", "sql_database"):
                if not getattr(self, name):
                    errors.append(f"{name.upper()} is required for SQL Server mode")
            if self.sql_auth_mode not in {"sql_login", "azure_identity"}:
                errors.append("SQL_AUTH_MODE must be sql_login or azure_identity")
            elif self.sql_auth_mode == "sql_login":
                for name in ("sql_user", "sql_password"):
                    if not getattr(self, name):
                        errors.append(f"{name.upper()} is required for SQL login mode")
            elif self.app_env == "production" and not self.azure_client_id:
                errors.append("AZURE_CLIENT_ID is required for production Azure identity SQL mode")
        if self.app_env == "production" and not self.session_redis_url:
            errors.append("SESSION_REDIS_URL is required for production server-side sessions")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
