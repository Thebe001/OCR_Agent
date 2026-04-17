"""Application settings loaded from environment variables."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development")
    app_port: int = Field(default=8000)
    debug: bool = Field(default=True)
    log_level: str = Field(default="DEBUG")

    erpnext_base_url: str = Field(default="http://localhost:8080")
    erpnext_api_key: str = Field(default="")
    erpnext_api_secret: str = Field(default="")

    azure_ocr_endpoint: str = Field(default="")
    azure_ocr_key: str = Field(default="")
    ocr_provider: str = Field(default="mock")

    default_tenant_id: str = Field(default="test-florist-001")
    allowed_origins: str = Field(default="*")

    @field_validator("app_env", "log_level", "erpnext_base_url", "azure_ocr_endpoint", "ocr_provider", "default_tenant_id", "allowed_origins", mode="before")
    @classmethod
    def _strip_strings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ocr_provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        return value.lower()


settings = Settings()
