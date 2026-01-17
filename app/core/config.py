from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import AnyUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json  # local import to avoid unused in production paths

                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except Exception:  # noqa: BLE001
                pass
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]
    return [str(value).strip()]


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "prod"] = Field(default="dev", validation_alias="APP_ENV")
    app_name: str = Field(default="anime-platform-backend", validation_alias="APP_NAME")
    api_v1_prefix: str = Field(default="/v1", validation_alias="API_V1_PREFIX")

    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_json: bool = Field(default=True, validation_alias="LOG_JSON")

    docs_enabled: bool = Field(default=True, validation_alias="DOCS_ENABLED")

    cors_allow_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ALLOW_ORIGINS")
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "OPTIONS"], validation_alias="CORS_ALLOW_METHODS")
    cors_allow_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "Accept", "Accept-Language", "X-Request-ID", "X-Locale"],
        validation_alias="CORS_ALLOW_HEADERS",
    )
    cors_allow_credentials: bool = Field(default=False, validation_alias="CORS_ALLOW_CREDENTIALS")

    enable_security_headers: bool = Field(default=True, validation_alias="ENABLE_SECURITY_HEADERS")

    default_locale: Literal["ru", "uz"] = Field(default="ru", validation_alias="DEFAULT_LOCALE")
    locale_header: str = Field(default="X-Locale", validation_alias="LOCALE_HEADER")

    max_upload_bytes: int = Field(default=5_000_000, validation_alias="MAX_UPLOAD_BYTES")
    upload_read_chunk_size: int = Field(default=64 * 1024, validation_alias="UPLOAD_READ_CHUNK_SIZE")
    allowed_image_mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"],
        validation_alias="ALLOWED_IMAGE_MIME_TYPES",
    )
    max_image_pixels: int = Field(default=20_000_000, validation_alias="MAX_IMAGE_PIXELS")
    max_image_width: int = Field(default=8000, validation_alias="MAX_IMAGE_WIDTH")
    max_image_height: int = Field(default=8000, validation_alias="MAX_IMAGE_HEIGHT")

    postgres_dsn: SecretStr = Field(..., validation_alias="POSTGRES_DSN")
    db_pool_size: int = Field(default=10, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, validation_alias="DB_MAX_OVERFLOW")
    db_pool_timeout_seconds: int = Field(default=30, validation_alias="DB_POOL_TIMEOUT_SECONDS")
    db_command_timeout_seconds: int = Field(default=30, validation_alias="DB_COMMAND_TIMEOUT_SECONDS")
    repository_timeout_seconds: float = Field(default=2.5, validation_alias="REPOSITORY_TIMEOUT_SECONDS")

    redis_dsn: SecretStr = Field(..., validation_alias="REDIS_DSN")
    redis_connect_timeout_seconds: float = Field(default=2.0, validation_alias="REDIS_CONNECT_TIMEOUT_SECONDS")
    redis_operation_timeout_seconds: float = Field(default=1.0, validation_alias="REDIS_OPERATION_TIMEOUT_SECONDS")
    redis_cache_ttl_seconds: int = Field(default=24 * 3600, validation_alias="REDIS_CACHE_TTL_SECONDS")
    redis_image_dedupe_ttl_seconds: int = Field(default=10 * 60, validation_alias="REDIS_IMAGE_DEDUPE_TTL_SECONDS")

    rate_limit_enabled: bool = Field(default=False, validation_alias="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(default=60, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, validation_alias="RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_key_prefix: str = Field(default="rl:", validation_alias="RATE_LIMIT_KEY_PREFIX")
    trusted_proxy_headers: bool = Field(default=False, validation_alias="TRUSTED_PROXY_HEADERS")

    ollama_base_url: AnyUrl = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:32b", validation_alias="OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(default=20.0, validation_alias="OLLAMA_TIMEOUT_SECONDS")
    ollama_temperature: float = Field(default=0.2, validation_alias="OLLAMA_TEMPERATURE")

    clip_model_path: str = Field(..., validation_alias="CLIP_MODEL_PATH")
    clip_device: str = Field(default="cuda", validation_alias="CLIP_DEVICE")
    clip_use_fp16: bool = Field(default=True, validation_alias="CLIP_USE_FP16")
    clip_concurrency: int = Field(default=2, validation_alias="CLIP_CONCURRENCY")
    clip_top_k: int = Field(default=5, validation_alias="CLIP_TOP_K")
    clip_confidence_threshold: float = Field(default=0.82, validation_alias="CLIP_CONFIDENCE_THRESHOLD")
    clip_inference_timeout_seconds: float = Field(default=7.0, validation_alias="CLIP_INFERENCE_TIMEOUT_SECONDS")
    clip_index_path: str | None = Field(default=None, validation_alias="CLIP_INDEX_PATH")
    clip_index_build_on_startup: bool = Field(default=True, validation_alias="CLIP_INDEX_BUILD_ON_STARTUP")
    clip_text_batch_size: int = Field(default=256, validation_alias="CLIP_TEXT_BATCH_SIZE")

    @field_validator(
        "cors_allow_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        "allowed_image_mime_types",
        mode="before",
    )
    @classmethod
    def _validate_csv_lists(cls, v: Any) -> list[str]:
        return _parse_csv_list(v)

    @model_validator(mode="after")
    def _validate_ranges(self) -> "BaseAppSettings":
        if self.max_upload_bytes <= 0:
            raise ValueError("MAX_UPLOAD_BYTES must be positive")
        if self.upload_read_chunk_size <= 0:
            raise ValueError("UPLOAD_READ_CHUNK_SIZE must be positive")
        if self.max_image_pixels <= 0:
            raise ValueError("MAX_IMAGE_PIXELS must be positive")
        if self.max_image_width <= 0 or self.max_image_height <= 0:
            raise ValueError("MAX_IMAGE_WIDTH and MAX_IMAGE_HEIGHT must be positive")
        if not (0.0 < self.clip_confidence_threshold <= 1.0):
            raise ValueError("CLIP_CONFIDENCE_THRESHOLD must be within (0, 1]")
        if self.clip_top_k <= 0:
            raise ValueError("CLIP_TOP_K must be positive")
        if self.clip_concurrency <= 0:
            raise ValueError("CLIP_CONCURRENCY must be positive")
        if self.rate_limit_requests <= 0 or self.rate_limit_window_seconds <= 0:
            raise ValueError("rate limit values must be positive")
        if self.ollama_timeout_seconds <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be positive")
        if self.redis_operation_timeout_seconds <= 0 or self.redis_connect_timeout_seconds <= 0:
            raise ValueError("redis timeout values must be positive")
        return self

    def postgres_dsn_plain(self) -> str:
        return self.postgres_dsn.get_secret_value()

    def redis_dsn_plain(self) -> str:
        return self.redis_dsn.get_secret_value()


class DevSettings(BaseAppSettings):
    docs_enabled: bool = Field(default=True, validation_alias="DOCS_ENABLED")


class ProdSettings(BaseAppSettings):
    docs_enabled: bool = Field(default=False, validation_alias="DOCS_ENABLED")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_allow_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ALLOW_ORIGINS")


Settings = BaseAppSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = (os.getenv("APP_ENV") or "dev").strip().lower()
    if env == "prod":
        return ProdSettings()
    return DevSettings()
