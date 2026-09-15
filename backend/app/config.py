from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'urbanagent.db').as_posix()}"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_excel_uncompressed_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_import_rows: int = Field(default=10_000, gt=0)
    openai_api_key: str = ""
    openai_model: str = ""
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=5)
    classification_review_threshold: float = Field(default=0.70, ge=0, le=1)
    validation_review_threshold: float = Field(default=0.70, ge=0, le=1)
    trend_min_feedback: int = Field(default=3, gt=0)
    spike_min_current_count: int = Field(default=3, gt=0)
    spike_percent_increase: float = Field(default=50.0, ge=0)
    recovery_high_score: int = Field(default=5, gt=0)
    recovery_critical_score: int = Field(default=9, gt=0)
    categories_path: Path = ROOT / "data" / "reference" / "categories.json"
    business_rules_path: Path = ROOT / "data" / "reference" / "business_rules.json"
