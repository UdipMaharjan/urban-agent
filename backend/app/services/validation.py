from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..agents.validator import ValidationAgent
from ..models import (
    FeedbackAnalysis,
    FeedbackValidation,
    ValidationCategory,
    ValidationIssue,
)
from ..schemas import FeedbackValidationRead, ValidationResult, ValidationStatus


def get_validation(session: Session, feedback_db_id: int) -> FeedbackValidation | None:
    return session.scalar(
        select(FeedbackValidation)
        .join(FeedbackValidation.analysis)
        .where(FeedbackAnalysis.feedback_id == feedback_db_id)
        .options(
            selectinload(FeedbackValidation.analysis).selectinload(FeedbackAnalysis.feedback),
            selectinload(FeedbackValidation.categories),
            selectinload(FeedbackValidation.issues),
            selectinload(FeedbackValidation.recovery_case),
        )
    )


def save_validation(
    session: Session,
    analysis: FeedbackAnalysis,
    result: ValidationResult,
    model_used: str,
) -> FeedbackValidation:
    validation = get_validation(session, analysis.feedback_id)
    if validation is None:
        validation = FeedbackValidation(analysis=analysis)
        session.add(validation)
    else:
        validation.recovery_case = None
        validation.categories.clear()
        validation.issues.clear()
        session.flush()

    validation.validation_status = result.validation_status.value
    validation.overall_confidence = result.overall_confidence
    validation.requires_human_review = result.requires_human_review
    validation.validated_sentiment = result.validated_sentiment.value
    validation.validated_severity = result.validated_severity.value
    validation.validation_summary = result.validation_summary
    validation.model_used = model_used
    validation.updated_at = datetime.now(UTC).replace(tzinfo=None)
    validation.categories.extend(
        ValidationCategory(category=category) for category in result.validated_categories
    )
    validation.issues.extend(
        ValidationIssue(
            field=issue.field,
            issue_type=issue.issue_type.value,
            message=issue.message,
        )
        for issue in result.issues
    )

    if result.validation_status == ValidationStatus.APPROVED:
        analysis.feedback.processing_status = (
            "validation_review_required" if result.requires_human_review else "validated"
        )
    elif result.validation_status == ValidationStatus.REJECTED:
        analysis.feedback.processing_status = "validation_rejected"
    else:
        analysis.feedback.processing_status = "validation_review_required"

    session.commit()
    return get_validation(session, analysis.feedback_id)


def validation_response(validation: FeedbackValidation) -> FeedbackValidationRead:
    return FeedbackValidationRead(
        id=validation.id,
        analysis_id=validation.analysis_id,
        feedback_db_id=validation.analysis.feedback_id,
        feedback_id=validation.analysis.feedback.feedback_id,
        validation_status=validation.validation_status,
        overall_confidence=validation.overall_confidence,
        requires_human_review=validation.requires_human_review,
        validated_sentiment=validation.validated_sentiment,
        validated_severity=validation.validated_severity,
        validated_categories=[category.category for category in validation.categories],
        validation_summary=validation.validation_summary,
        model_used=validation.model_used,
        created_at=validation.created_at,
        updated_at=validation.updated_at,
        issues=validation.issues,
    )


def validate_and_save(
    session: Session, analysis: FeedbackAnalysis, agent: ValidationAgent
) -> FeedbackValidation:
    result = agent.validate(analysis)
    return save_validation(session, analysis, result, agent.llm.model)
