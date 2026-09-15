from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Feedback(Base):
    """Raw input plus ingestion/classification lifecycle status."""

    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("source", "feedback_id", name="uq_feedback_source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100), default="manual")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    feedback_text: Mapped[str] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    analysis: Mapped["FeedbackAnalysis | None"] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", uselist=False
    )


class FeedbackAnalysis(Base):
    """Current Classification Agent result for one raw feedback record."""

    __tablename__ = "feedback_analyses"
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('Positive', 'Neutral', 'Negative')",
            name="ck_analysis_sentiment",
        ),
        CheckConstraint("severity IN ('Low', 'Medium', 'High')", name="ck_analysis_severity"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_analysis_confidence"),
        CheckConstraint("analysis_status = 'completed'", name="ck_analysis_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), unique=True, index=True
    )
    primary_category: Mapped[str] = mapped_column(String(100), index=True)
    sentiment: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    summary: Mapped[str] = mapped_column(String(500))
    is_mixed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    analysis_status: Mapped[str] = mapped_column(String(30), default="completed")
    model_used: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    feedback: Mapped[Feedback] = relationship(back_populates="analysis")
    aspects: Mapped[list["FeedbackAspect"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="FeedbackAspect.id"
    )
    validation: Mapped["FeedbackValidation | None"] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", uselist=False
    )


class FeedbackAspect(Base):
    """One evidence-backed category/aspect within a classification."""

    __tablename__ = "feedback_aspects"
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('Positive', 'Neutral', 'Negative')",
            name="ck_aspect_sentiment",
        ),
        CheckConstraint("severity IN ('Low', 'Medium', 'High')", name="ck_aspect_severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_analyses.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(100), index=True)
    sentiment: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    evidence_text: Mapped[str] = mapped_column(String(500))

    analysis: Mapped[FeedbackAnalysis] = relationship(back_populates="aspects")


class FeedbackValidation(Base):
    """Independent Validation Agent result for the current classification."""

    __tablename__ = "feedback_validations"
    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('approved', 'approved_with_changes', "
            "'needs_review', 'rejected')",
            name="ck_validation_status",
        ),
        CheckConstraint(
            "overall_confidence >= 0 AND overall_confidence <= 1",
            name="ck_validation_confidence",
        ),
        CheckConstraint(
            "validated_sentiment IN ('Positive', 'Neutral', 'Negative', 'Mixed')",
            name="ck_validation_sentiment",
        ),
        CheckConstraint(
            "validated_severity IN ('Low', 'Medium', 'High')",
            name="ck_validation_severity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_analyses.id", ondelete="CASCADE"), unique=True, index=True
    )
    validation_status: Mapped[str] = mapped_column(String(30), index=True)
    overall_confidence: Mapped[float] = mapped_column(Float)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    validated_sentiment: Mapped[str] = mapped_column(String(20))
    validated_severity: Mapped[str] = mapped_column(String(20))
    validation_summary: Mapped[str] = mapped_column(String(500))
    model_used: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    analysis: Mapped[FeedbackAnalysis] = relationship(back_populates="validation")
    categories: Mapped[list["ValidationCategory"]] = relationship(
        back_populates="validation",
        cascade="all, delete-orphan",
        order_by="ValidationCategory.id",
    )
    issues: Mapped[list["ValidationIssue"]] = relationship(
        back_populates="validation",
        cascade="all, delete-orphan",
        order_by="ValidationIssue.id",
    )
    recovery_case: Mapped["RecoveryCase | None"] = relationship(
        back_populates="validation", cascade="all, delete-orphan", uselist=False
    )


class ValidationCategory(Base):
    """One category accepted or corrected by the Validation Agent."""

    __tablename__ = "validation_categories"
    __table_args__ = (UniqueConstraint("validation_id", "category", name="uq_validation_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_validations.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(100), index=True)

    validation: Mapped[FeedbackValidation] = relationship(back_populates="categories")


class ValidationIssue(Base):
    """A structured concern found while validating a classification."""

    __tablename__ = "validation_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_validations.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(100))
    issue_type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))

    validation: Mapped[FeedbackValidation] = relationship(back_populates="issues")


class BusinessRecommendation(Base):
    """Evidence-backed AI proposal awaiting a management decision."""

    __tablename__ = "business_recommendations"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('Low', 'Medium', 'High', 'Critical')",
            name="ck_recommendation_priority",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_recommendation_approval",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_recommendation_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    problem_summary: Mapped[str] = mapped_column(String(500))
    recommendation: Mapped[str] = mapped_column(Text)
    business_rationale: Mapped[str] = mapped_column(Text)
    evidence_count: Mapped[int]
    requires_management_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    confidence: Mapped[float] = mapped_column(Float)
    trend_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model_used: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    evidence: Mapped[list["RecommendationEvidence"]] = relationship(
        back_populates="recommendation_record",
        cascade="all, delete-orphan",
        order_by="RecommendationEvidence.id",
    )
    approval_events: Mapped[list["RecommendationApprovalEvent"]] = relationship(
        back_populates="recommendation_record",
        cascade="all, delete-orphan",
        order_by="RecommendationApprovalEvent.id",
    )


class RecommendationEvidence(Base):
    """Links a recommendation to each feedback record supporting its trend."""

    __tablename__ = "recommendation_evidence"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "feedback_db_id", name="uq_recommendation_feedback"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("business_recommendations.id", ondelete="CASCADE"), index=True
    )
    feedback_db_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), index=True
    )

    recommendation_record: Mapped[BusinessRecommendation] = relationship(back_populates="evidence")
    feedback: Mapped[Feedback] = relationship()


class RecommendationApprovalEvent(Base):
    """Append-only history of human recommendation decisions."""

    __tablename__ = "recommendation_approval_events"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_recommendation_decision",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("business_recommendations.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

    recommendation_record: Mapped[BusinessRecommendation] = relationship(
        back_populates="approval_events"
    )


class RecoveryCase(Base):
    """Deterministic customer-risk evaluation tied to one trusted validation."""

    __tablename__ = "recovery_cases"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('Low', 'Medium', 'High', 'Critical')",
            name="ck_recovery_risk",
        ),
        CheckConstraint(
            "status IN ('open', 'under_review', 'approved_for_contact', 'resolved', 'dismissed')",
            name="ck_recovery_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_validations.id", ondelete="CASCADE"), unique=True, index=True
    )
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    risk_score: Mapped[int]
    recovery_required: Mapped[bool] = mapped_column(Boolean, index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    validation: Mapped[FeedbackValidation] = relationship(back_populates="recovery_case")
    reasons: Mapped[list["RecoveryReason"]] = relationship(
        back_populates="recovery_case",
        cascade="all, delete-orphan",
        order_by="RecoveryReason.id",
    )


class RecoveryReason(Base):
    """One explainable factor contributing to a recovery risk level."""

    __tablename__ = "recovery_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    recovery_case_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))

    recovery_case: Mapped[RecoveryCase] = relationship(back_populates="reasons")
