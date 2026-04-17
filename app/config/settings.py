"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "debug", "development"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    debug: bool = _bool_env("DEBUG", True)
    log_level: str = os.getenv("LOG_LEVEL", "DEBUG")

    erpnext_base_url: str = os.getenv("ERPNEXT_BASE_URL", "http://localhost:8080")
    erpnext_api_key: str = os.getenv("ERPNEXT_API_KEY", "")
    erpnext_api_secret: str = os.getenv("ERPNEXT_API_SECRET", "")

    azure_ocr_endpoint: str = os.getenv("AZURE_OCR_ENDPOINT", "")
    azure_ocr_key: str = os.getenv("AZURE_OCR_KEY", "")
    ocr_provider: str = os.getenv("OCR_PROVIDER", "mock").strip().lower()

    default_tenant_id: str = os.getenv("DEFAULT_TENANT_ID", "test-florist-001")
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")


settings = Settings()
