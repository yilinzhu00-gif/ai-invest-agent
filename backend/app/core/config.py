from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the HTTP boundary, with safe local defaults."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "investment-agent-api"
    app_version: str = "0.1.0"
    api_v1_prefix: Literal["/api/v1"] = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_connect_timeout: float = 5.0
    max_request_body_bytes: int = Field(default=64 * 1024, gt=0)
    agent_run_timeout_seconds: int = Field(default=180, gt=0, le=3600)
    agent_max_steps: int = Field(default=8, gt=0, le=100)
    agent_runtime: Literal["langgraph", "crewai"] = "langgraph"
    agent_max_revisions: int = Field(default=1, ge=0, le=1)
    document_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0, le=50 * 1024 * 1024)
    document_max_pages: int = Field(default=500, gt=0, le=500)
    document_ocr_languages: str = "chi_sim+eng"
    document_table_merge_threshold: float = Field(default=0.90, ge=0, le=1)
    sse_heartbeat_seconds: int = Field(default=15, gt=0, le=60)
    chat_model: str = "gpt-4o-mini"
    review_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    model_run_max_tokens: int = Field(default=16_000, gt=0)
    model_run_max_cost_microusd: int = Field(default=1_000_000, gt=0)

    @model_validator(mode="after")
    def require_database_url_in_production(self) -> "Settings":
        if self.app_env == "production" and not self.database_url:
            raise ValueError("DATABASE_URL is required when APP_ENV is production")
        return self

    @field_validator("cors_origins")
    @classmethod
    def require_explicit_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain one or more explicit origins")
        return ",".join(origins)

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")

    @property
    def async_database_url(self) -> str | None:
        """Return a PostgreSQL URL that SQLAlchemy can use with asyncpg."""
        if self.database_url is None:
            return None
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url
