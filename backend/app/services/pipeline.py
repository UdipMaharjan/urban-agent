"""Business-level orchestration; agents and persistence remain in existing services."""

from collections.abc import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..agents.classifier import ClassificationAgent
from ..agents.validator import ValidationAgent
from ..models import Feedback, FeedbackAnalysis, FeedbackValidation
from ..schemas import PipelineBatchSummary, PipelineError, PipelineResult
from .analysis import analysis_response, classify_and_save, get_analysis
from .analytics import TRUSTED_VALIDATION_STATUSES
from .llm import LLMInvalidResponseError, LLMServiceError, LLMTimeoutError
from .recovery import RecoveryService, recovery_case_response
from .validation import get_validation, validate_and_save, validation_response


def pending_ids(session: Session) -> list[int]:
    return list(
        session.scalars(
            select(Feedback.id)
            .outerjoin(Feedback.analysis)
            .outerjoin(FeedbackAnalysis.validation)
            .where(
                or_(
                    FeedbackAnalysis.id.is_(None),
                    FeedbackAnalysis.analysis_status != "completed",
                    FeedbackValidation.id.is_(None),
                    Feedback.processing_status == "recovery_failed",
                )
            )
            .order_by(Feedback.id)
        )
    )


class AnalysisPipeline:
    def __init__(
        self,
        session: Session,
        classifier: Callable[[], ClassificationAgent],
        validator: Callable[[], ValidationAgent],
        recovery: RecoveryService,
    ):
        self.session = session
        self.classifier = classifier
        self.validator = validator
        self.recovery = recovery

    def analyze(self, feedback_db_id: int, *, force: bool = False) -> PipelineResult:
        feedback = self.session.get(Feedback, feedback_db_id)
        if feedback is None:
            raise LookupError("Feedback not found.")
        external_id = feedback.feedback_id
        analysis = get_analysis(self.session, feedback_db_id)
        validation = get_validation(self.session, feedback_db_id)
        reused = not force and analysis is not None and validation is not None
        stage = "classification"
        error = None
        case = None
        try:
            if force or analysis is None or analysis.analysis_status != "completed":
                analysis = classify_and_save(self.session, feedback, self.classifier())
                validation = None
            stage = "validation"
            if validation is None:
                validation = validate_and_save(self.session, analysis, self.validator())
            stage = "recovery"
            if validation.validation_status in TRUSTED_VALIDATION_STATUSES:
                # Existing case decisions are reused unless re-analysis invalidated them.
                case = self.recovery.evaluate_validation(validation)
            if feedback.processing_status == "recovery_failed":
                feedback.processing_status = "validated"
                self.session.commit()
        except Exception as exc:
            # A failed stage must not roll back previously committed stages/records.
            # Never return arbitrary exception text: providers may include request data.
            self.session.rollback()
            if isinstance(exc, LLMTimeoutError):
                code, message = "timeout", "Analysis timed out. Retry to resume completed work."
            elif isinstance(exc, LLMInvalidResponseError):
                code, message = (
                    "invalid_response",
                    "The AI response could not be validated. Please retry.",
                )
            elif isinstance(exc, LLMServiceError) or getattr(exc, "status_code", None) == 503:
                code, message = (
                    "unavailable",
                    "Analysis is unavailable. Check the backend AI key, model and connection.",
                )
            else:
                code, message = (
                    "processing_error",
                    "This processing step could not be saved. Please retry.",
                )
            error = PipelineError(stage=stage, code=code, message=message)
            analysis = get_analysis(self.session, feedback_db_id)
            validation = get_validation(self.session, feedback_db_id)
            feedback = self.session.get(Feedback, feedback_db_id)
            # Keep a previous complete result valid if forced classification failed.
            if validation is None or stage == "recovery":
                feedback.processing_status = f"{stage}_failed"
                self.session.commit()
        review = bool(
            (analysis and analysis.requires_review)
            or (
                validation
                and (
                    validation.requires_human_review
                    or validation.validation_status in {"needs_review", "rejected"}
                )
            )
        )
        return PipelineResult(
            feedback_db_id=feedback_db_id,
            feedback_id=external_id,
            status="failed" if error else "requires_review" if review else "completed",
            classification_status="completed" if analysis else "pending",
            validation_status=validation.validation_status if validation else None,
            requires_human_review=review,
            reused=reused,
            analysis=analysis_response(analysis) if analysis else None,
            validation=validation_response(validation) if validation else None,
            recovery=recovery_case_response(case) if case else None,
            error=error,
        )

    def analyze_pending(self) -> PipelineBatchSummary:
        ids = pending_ids(self.session)
        summary = PipelineBatchSummary(total_pending=len(ids))
        for feedback_db_id in ids:
            result = self.analyze(feedback_db_id)
            summary.results.append(result)
            if result.status == "failed":
                summary.failed += 1
                field = f"{result.error.stage}_failures"
                setattr(summary, field, getattr(summary, field) + 1)
            elif result.requires_human_review:
                summary.requires_review += 1
            else:
                summary.completed += 1
        return summary
