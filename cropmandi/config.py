from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/cropmandi.db"
    cropmandi_coffee_pdf_dir: str = ""
    cropmandi_http_timeout: float = 45.0
    data_dir: Path = ROOT / "data"
    data_gov_api_key: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""


def get_settings() -> Settings:
    return Settings()
