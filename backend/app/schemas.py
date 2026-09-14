from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: Annotated[str, Field(min_length=1, max_length=200)]
    source: Annotated[str, Field(min_length=1, max_length=100)] = "manual"
    submitted_at: datetime | None = None
    rating: Annotated[float, Field(allow_inf_nan=False)] | None = None
    customer_name: Annotated[str, Field(max_length=200)] | None = None
    customer_email: Annotated[str, Field(max_length=320)] | None = None
    feedback_text: Annotated[str, Field(min_length=1, max_length=50_000)]

    @field_validator("feedback_id", "source", mode="before")
    @classmethod
    def normalize_keys(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("feedback_text")
    @classmethod
    def require_text(cls, value):
        if not value.strip():
            raise ValueError("feedback_text must contain non-whitespace text")
        return value

    @field_validator("rating", mode="before")
    @classmethod
    def reject_boolean_rating(cls, value):
        if isinstance(value, bool):
            raise ValueError("rating must be a finite number, not a boolean")
        return value

    @field_validator("submitted_at", mode="before")
    @classmethod
    def parse_date(cls, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("submitted_at must be an ISO 8601 date or datetime") from exc
        raise ValueError("submitted_at must be an Excel date or ISO 8601 text, not a number")

    @field_validator("submitted_at")
    @classmethod
    def normalize_date(cls, value):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def storage_values(self):
        values = self.model_dump()
        if self.submitted_at is not None:
            values["submitted_at"] = self.submitted_at.replace(tzinfo=None)
        return values


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feedback_id: str
    source: str
    submitted_at: datetime | None
    rating: float | None
    customer_name: str | None
    customer_email: str | None
    feedback_text: str
    processing_status: str
    created_at: datetime

    @field_validator("submitted_at", "created_at")
    @classmethod
    def utc_response(cls, value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ImportIssue(BaseModel):
    row: int
    feedback_id: str | None = None
    code: Literal["validation_error", "duplicate", "conflict", "blank_row"]
    message: str


class ImportSummary(BaseModel):
    total_rows: int
    imported_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    errors: list[ImportIssue] = Field(default_factory=list)


class Sentiment(StrEnum):
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class Severity(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class ClassificationAspect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Annotated[str, Field(min_length=1, max_length=100)]
    sentiment: Sentiment
    severity: Severity
    evidence_text: Annotated[str, Field(min_length=1, max_length=500)]


class ClassificationResult(BaseModel):
    """Strict schema requested from the model before business-rule validation."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: Annotated[str, Field(min_length=1, max_length=200)]
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    sentiment: Sentiment
    severity: Severity
    primary_category: Annotated[str, Field(min_length=1, max_length=100)]
    is_mixed: bool
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    requires_review: bool
    aspects: Annotated[list[ClassificationAspect], Field(min_length=1, max_length=10)]


class FeedbackAspectRead(ClassificationAspect):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FeedbackAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feedback_db_id: int
    feedback_id: str
    primary_category: str
    sentiment: Sentiment
    severity: Severity
    summary: str
    is_mixed: bool
    confidence: float
    requires_review: bool
    analysis_status: Literal["completed"]
    model_used: str
    created_at: datetime
    updated_at: datetime
    aspects: list[FeedbackAspectRead]

    @field_validator("created_at", "updated_at")
    @classmethod
    def analysis_utc_response(cls, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class BatchClassificationError(BaseModel):
    feedback_db_id: int
    feedback_id: str
    message: str


class BatchClassificationSummary(BaseModel):
    total: int
    processed: int
    failed: int
    requires_review: int
    errors: list[BatchClassificationError] = Field(default_factory=list)
