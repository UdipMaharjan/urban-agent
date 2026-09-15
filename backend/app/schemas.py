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


class ValidationStatus(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_CHANGES = "approved_with_changes"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class ValidatedSentiment(StrEnum):
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"
    MIXED = "Mixed"


class ValidationIssueType(StrEnum):
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    MISSING = "missing"
    INCONSISTENT = "inconsistent"
    FABRICATED = "fabricated"
    AMBIGUOUS = "ambiguous"
    UNREASONABLE = "unreasonable"


class ValidationIssueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Annotated[str, Field(min_length=1, max_length=100)]
    issue_type: ValidationIssueType
    message: Annotated[str, Field(min_length=1, max_length=500)]


class ValidationResult(BaseModel):
    """Strict schema requested from the independent Validation Agent."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: Annotated[str, Field(min_length=1, max_length=200)]
    validation_status: ValidationStatus
    overall_confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    requires_human_review: bool
    issues: Annotated[list[ValidationIssueResult], Field(max_length=30)]
    validated_sentiment: ValidatedSentiment
    validated_severity: Severity
    validated_categories: Annotated[list[str], Field(min_length=1, max_length=10)]
    validation_summary: Annotated[str, Field(min_length=1, max_length=500)]


class ValidationIssueRead(ValidationIssueResult):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FeedbackValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: int
    feedback_db_id: int
    feedback_id: str
    validation_status: ValidationStatus
    overall_confidence: float
    requires_human_review: bool
    validated_sentiment: ValidatedSentiment
    validated_severity: Severity
    validated_categories: list[str]
    validation_summary: str
    model_used: str
    created_at: datetime
    updated_at: datetime
    issues: list[ValidationIssueRead]

    @field_validator("created_at", "updated_at")
    @classmethod
    def validation_utc_response(cls, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class BatchValidationError(BaseModel):
    feedback_db_id: int
    feedback_id: str
    message: str


class BatchValidationSummary(BaseModel):
    total: int
    validated: int
    needs_review: int
    rejected: int
    failed: int
    errors: list[BatchValidationError] = Field(default_factory=list)


class TimelinePeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int
    mixed: int


class SeverityBreakdown(BaseModel):
    low: int
    medium: int
    high: int


class SentimentAnalytics(SentimentBreakdown):
    total: int
    positive_percentage: float
    neutral_percentage: float
    negative_percentage: float
    mixed_percentage: float


class SourceCount(BaseModel):
    source: str
    count: int
    percentage: float


class CategoryCount(BaseModel):
    category: str
    count: int


class CategoryAnalyticsItem(BaseModel):
    category: str
    feedback_count: int
    aspect_count: int
    percentage: float
    aspect_percentage: float
    sentiment_counts: SentimentBreakdown
    severity_counts: SeverityBreakdown


class CategoryAnalytics(BaseModel):
    trusted_feedback_count: int
    total_aspect_count: int
    categories: list[CategoryAnalyticsItem]


class SeverityAnalytics(SeverityBreakdown):
    total: int
    high_severity_negative: int
    high_severity_by_category: list[CategoryCount]


class PatternItem(BaseModel):
    category: str
    sentiment: Literal["Positive", "Negative"]
    feedback_count: int
    recurring: bool
    supporting_feedback_ids: list[str]


class TrendAnalytics(BaseModel):
    threshold: int
    negative_patterns: list[PatternItem]
    positive_patterns: list[PatternItem]


class TimelinePoint(BaseModel):
    period_start: date
    total: int
    positive: int
    neutral: int
    negative: int
    mixed: int
    category_counts: list[CategoryCount]


class TimelineAnalytics(BaseModel):
    period: TimelinePeriod
    points: list[TimelinePoint]


class EmergingIssue(BaseModel):
    category: str
    status: Literal["spike", "new_emerging_issue"]
    previous_count: int
    current_count: int
    percentage_change: float | None
    supporting_feedback_ids: list[str]


class EmergingIssuesAnalytics(BaseModel):
    period: TimelinePeriod
    current_period_start: date | None
    previous_period_start: date | None
    minimum_current_count: int
    percentage_increase_threshold: float
    issues: list[EmergingIssue]


class AnalyticsOverview(BaseModel):
    total_feedback_count: int
    trusted_validated_feedback_count: int
    records_requiring_human_review: int
    rated_feedback_count: int
    average_rating: float | None
    total_aspect_count: int
    source_counts: list[SourceCount]
    recurring_negative_trend_count: int
    recurring_positive_pattern_count: int


class RecommendationPriority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RecommendationApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RecommendationDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RecommendationEvidenceSummary(BaseModel):
    feedback_id: str
    analysis_summary: str
    validation_summary: str
    validated_severity: Severity


class RecommendationBusinessContext(BaseModel):
    relevant_rules: list[str]
    management_preference: str
    decision_authority: str


class RecommendationTrendInput(BaseModel):
    category: str
    feedback_count: int
    negative_count: int
    high_severity_count: int
    supporting_feedback_ids: list[str]
    supporting_evidence: list[RecommendationEvidenceSummary]
    business_context: RecommendationBusinessContext
    emerging_issue_status: Literal["spike", "new_emerging_issue"] | None = None


class RecommendationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Annotated[str, Field(min_length=1, max_length=100)]
    priority: RecommendationPriority
    problem_summary: Annotated[str, Field(min_length=1, max_length=500)]
    recommendation: Annotated[str, Field(min_length=1, max_length=2000)]
    business_rationale: Annotated[str, Field(min_length=1, max_length=2000)]
    supporting_feedback_ids: Annotated[list[str], Field(min_length=1, max_length=1000)]
    evidence_count: Annotated[int, Field(gt=0)]
    requires_management_approval: bool
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class RecommendationApprovalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_status: RecommendationDecision


class RecommendationApprovalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision: RecommendationDecision
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def approval_utc_response(cls, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class BusinessRecommendationRead(BaseModel):
    id: int
    category: str
    priority: RecommendationPriority
    problem_summary: str
    recommendation: str
    business_rationale: str
    evidence_count: int
    supporting_feedback_ids: list[str]
    requires_management_approval: bool
    approval_status: RecommendationApprovalStatus
    confidence: float
    model_used: str
    created_at: datetime
    updated_at: datetime
    approval_history: list[RecommendationApprovalEventRead]

    @field_validator("created_at", "updated_at")
    @classmethod
    def recommendation_utc_response(cls, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class RecommendationGenerationError(BaseModel):
    category: str
    message: str


class RecommendationGenerationSummary(BaseModel):
    eligible_trends: int
    generated: int
    skipped_duplicates: int
    failed: int
    recommendations: list[BusinessRecommendationRead] = Field(default_factory=list)
    errors: list[RecommendationGenerationError] = Field(default_factory=list)


class RecoveryRiskLevel(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RecoveryStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    APPROVED_FOR_CONTACT = "approved_for_contact"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class RecoveryStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RecoveryStatus
    assigned_to: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class RecoveryReasonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reason: str


class RecoveryCaseRead(BaseModel):
    id: int
    feedback_db_id: int
    feedback_id: str
    risk_level: RecoveryRiskLevel
    risk_score: int
    recovery_required: bool
    status: RecoveryStatus
    reasons: list[RecoveryReasonRead]
    suggested_action: str | None
    response_draft: str | None
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    @field_validator("created_at", "updated_at", "resolved_at")
    @classmethod
    def recovery_utc_response(cls, value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class RecoveryBatchSummary(BaseModel):
    total: int
    evaluated: int
    recovery_required: int
    low_risk: int


class PipelineError(BaseModel):
    stage: Literal["classification", "validation", "recovery"]
    code: Literal["timeout", "unavailable", "invalid_response", "processing_error"]
    message: str


class PipelineResult(BaseModel):
    feedback_db_id: int
    feedback_id: str
    status: Literal["completed", "requires_review", "failed"]
    classification_status: Literal["pending", "completed"]
    validation_status: ValidationStatus | None = None
    requires_human_review: bool = False
    reused: bool = False
    analysis: FeedbackAnalysisRead | None = None
    validation: FeedbackValidationRead | None = None
    recovery: RecoveryCaseRead | None = None
    error: PipelineError | None = None


class PipelineBatchSummary(BaseModel):
    total_pending: int = 0
    completed: int = 0
    requires_review: int = 0
    failed: int = 0
    classification_failures: int = 0
    validation_failures: int = 0
    recovery_failures: int = 0
    results: list[PipelineResult] = Field(default_factory=list)


class PipelineState(BaseModel):
    total: int
    pending: int
    requires_review: int
    is_running: bool
