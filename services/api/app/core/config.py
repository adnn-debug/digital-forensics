"""Centralized configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Environment
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    PROJECT_NAME: str = "PS-05 Digital Evidence Platform"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "ps05-insecure-dev-key-change-in-production-min32chars!"

    # Server Binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://forensic_admin:forensic_secure_pass_2026@localhost:5432/ps05_evidence_db",
        description="Async database connection URI (PostgreSQL or SQLite async)",
    )

    # Redis Broker / Cache
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Private Local Storage Paths
    STORAGE_BASE_PATH: Path = Field(
        default=Path("./storage"),
        description="Root private vault directory",
    )
    STORAGE_ORIGINALS_PATH: Path = Field(
        default=Path("./storage/originals"),
        description="Vault for immutable original evidence bitstreams",
    )
    STORAGE_ARTIFACTS_PATH: Path = Field(
        default=Path("./storage/artifacts"),
        description="Directory for derivative artifacts (heatmaps, plots, frames)",
    )
    STORAGE_REPORTS_PATH: Path = Field(
        default=Path("./storage/reports"),
        description="Directory for compiled courtroom PDF reports",
    )
    STORAGE_TMP_PATH: Path = Field(
        default=Path("./storage/tmp"),
        description="Scratch directory for upload staging and temporary files",
    )
    STORAGE_MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=5 * 1024 * 1024 * 1024,  # 5 GB
        description="Maximum upload stream size in bytes",
    )

    # Forensic Tool Subprocess Settings
    EXIFTOOL_PATH: str = Field(
        default="exiftool",
        description="Binary executable name or absolute path for Phil Harvey's ExifTool",
    )
    FFPROBE_PATH: str = Field(
        default="ffprobe",
        description="Binary executable name or absolute path for FFprobe",
    )
    FORENSIC_SUBPROCESS_TIMEOUT_SECONDS: int = Field(
        default=30,
        description="Strict execution timeout in seconds for forensic CLI subprocesses",
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Reject development credentials and unsafe local defaults in deployed environments."""
        if self.ENVIRONMENT in ("staging", "production"):
            if self.DEBUG:
                raise ValueError("DEBUG must be false in staging and production.")
            if (
                len(self.SECRET_KEY) < 32
                or self.SECRET_KEY.startswith("ps05-insecure")
                or "CHANGE_ME" in self.SECRET_KEY
            ):
                raise ValueError("Configure a unique random SECRET_KEY of at least 32 characters.")
            if (
                "forensic_secure_pass_2026" in self.DATABASE_URL
                or "CHANGE_ME" in self.DATABASE_URL
                or self.DATABASE_URL.startswith("sqlite")
            ):
                raise ValueError("Configure a production database URL with a unique password.")
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                raise ValueError("A deployed environment must not use a localhost database.")
            if "localhost" in self.REDIS_URL or "127.0.0.1" in self.REDIS_URL:
                raise ValueError("A deployed environment must not use a localhost Redis instance.")
        return self

    @field_validator(
        "STORAGE_BASE_PATH",
        "STORAGE_ORIGINALS_PATH",
        "STORAGE_ARTIFACTS_PATH",
        "STORAGE_REPORTS_PATH",
        "STORAGE_TMP_PATH",
        mode="after",
    )
    @classmethod
    def resolve_paths(cls, value: Path) -> Path:
        """Resolve paths to absolute paths for security and consistency."""
        return value.resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()
