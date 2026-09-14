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
