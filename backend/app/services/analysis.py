from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..agents.classifier import ClassificationAgent
from ..models import Feedback, FeedbackAnalysis, FeedbackAspect
from ..schemas import ClassificationResult, FeedbackAnalysisRead


def get_analysis(session: Session, feedback_db_id: int) -> FeedbackAnalysis | None:
    return session.scalar(
        select(FeedbackAnalysis)
        .where(FeedbackAnalysis.feedback_id == feedback_db_id)
        .options(selectinload(FeedbackAnalysis.aspects), selectinload(FeedbackAnalysis.feedback))
    )


def save_classification(
    session: Session,
    feedback: Feedback,
    result: ClassificationResult,
    model_used: str,
) -> FeedbackAnalysis:
    analysis = get_analysis(session, feedback.id)
    if analysis is None:
        analysis = FeedbackAnalysis(feedback=feedback)
        session.add(analysis)
    else:
        analysis.aspects.clear()
    analysis.primary_category = result.primary_category
    analysis.sentiment = result.sentiment.value
    analysis.severity = result.severity.value
    analysis.summary = result.summary
    analysis.is_mixed = result.is_mixed
    analysis.confidence = result.confidence
    analysis.requires_review = result.requires_review
    analysis.analysis_status = "completed"
    analysis.model_used = model_used
    analysis.updated_at = datetime.now(UTC).replace(tzinfo=None)
    analysis.aspects.extend(
        FeedbackAspect(
            category=aspect.category,
            sentiment=aspect.sentiment.value,
            severity=aspect.severity.value,
            evidence_text=aspect.evidence_text,
        )
        for aspect in result.aspects
    )
    feedback.processing_status = "classified"
    session.commit()
    return get_analysis(session, feedback.id)


def analysis_response(analysis: FeedbackAnalysis) -> FeedbackAnalysisRead:
    return FeedbackAnalysisRead(
        id=analysis.id,
        feedback_db_id=analysis.feedback_id,
        feedback_id=analysis.feedback.feedback_id,
        primary_category=analysis.primary_category,
        sentiment=analysis.sentiment,
        severity=analysis.severity,
        summary=analysis.summary,
        is_mixed=analysis.is_mixed,
        confidence=analysis.confidence,
        requires_review=analysis.requires_review,
        analysis_status=analysis.analysis_status,
        model_used=analysis.model_used,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        aspects=analysis.aspects,
    )


def classify_and_save(
    session: Session, feedback: Feedback, agent: ClassificationAgent
) -> FeedbackAnalysis:
    result = agent.classify(feedback)
    return save_classification(session, feedback, result, agent.llm.model)
