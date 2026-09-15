import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import FeedbackAnalysis, FeedbackValidation, RecoveryCase, RecoveryReason
from ..schemas import (
    RecoveryBatchSummary,
    RecoveryCaseRead,
    RecoveryRiskLevel,
    RecoveryStatus,
    RecoveryStatusUpdate,
)
from .analytics import TRUSTED_VALIDATION_STATUSES

CHURN_PHRASES = (
    "stop shopping",
    "never shop",
    "never buy",
    "lost me as a customer",
    "take my business elsewhere",
    "won't return",
    "will not return",
)
REPEATED_FAILURE_PHRASES = (
    "twice",
    "multiple times",
    "several times",
    "again",
    "repeatedly",
    "kept failing",
    "still not",
)
UNRESOLVED_SUPPORT_PHRASES = (
    "no response",
    "never responded",
    "without help",
    "no help",
    "not resolved",
    "still waiting",
)
DAMAGED_PRODUCT_PHRASES = (
    "arrived damaged",
    "damaged product",
    "defective",
    "broken",
    "stopped working",
)
SERIOUS_DELIVERY_PHRASES = (
    "next-day",
    "next day",
    "after four days",
    "late delivery",
    "delivery was late",
    "not arrived",
    "missing package",
)


class RecoveryError(RuntimeError):
    pass


class RecoveryNotTrustedError(RecoveryError):
    pass


class AmbiguousFeedbackIdError(RecoveryError):
    pass


class RecoveryService:
    """Creates explainable recovery evaluations from trusted validation data."""

    def __init__(self, session: Session, *, high_score: int, critical_score: int):
        if critical_score <= high_score:
            raise ValueError("recovery_critical_score must be greater than recovery_high_score")
        self.session = session
        self.high_score = high_score
        self.critical_score = critical_score

    def evaluate_feedback(
        self, external_feedback_id: str, source: str | None = None
    ) -> RecoveryCase:
        validations = self._validations_for_external_id(external_feedback_id, source)
        if not validations:
            raise RecoveryNotTrustedError(
                "Feedback must have an approved or approved_with_changes validation."
            )
        if len(validations) > 1:
            raise AmbiguousFeedbackIdError(
                "More than one source uses this feedback_id; provide the source query parameter."
            )
        return self.evaluate_validation(validations[0])

    def evaluate_validation(self, validation: FeedbackValidation) -> RecoveryCase:
        if validation.validation_status not in TRUSTED_VALIDATION_STATUSES:
            raise RecoveryNotTrustedError(
                "Feedback must have an approved or approved_with_changes validation."
            )
        existing = get_recovery_case_by_validation(self.session, validation.id)
        if existing is not None:
            return existing

        feedback = validation.analysis.feedback
        text = self._normalize(feedback.feedback_text)
        categories = {category.category for category in validation.categories}
        score = 0
        reasons = []

        if validation.validated_severity == "High":
            score += 5
            reasons.append("High-severity validated complaint")
        elif validation.validated_severity == "Medium":
            score += 2
            reasons.append("Medium-severity validated issue")

        if validation.validated_sentiment == "Negative":
            score += 2
            reasons.append("Negative validated sentiment")
        elif validation.validated_sentiment == "Mixed":
            score += 1
            reasons.append("Mixed feedback includes a negative experience")

        if self._contains_any(text, CHURN_PHRASES):
            score += 4
            reasons.append("Customer indicates intent to stop shopping")
        if self._contains_any(text, REPEATED_FAILURE_PHRASES):
            score += 2
            reasons.append("Feedback describes repeated failure or contact")
        if len(categories) > 1:
            score += 1
            reasons.append("Multiple validated experience categories are affected")
        if "Customer Service" in categories and self._contains_any(
            text, UNRESOLVED_SUPPORT_PHRASES
        ):
            score += 2
            reasons.append("Customer-service issue appears unresolved")
        if "wrong product" in text:
            score += 2
            reasons.append("Wrong product received")
        if "Product Quality" in categories and self._contains_any(text, DAMAGED_PRODUCT_PHRASES):
            score += 2
            reasons.append("Damaged, defective, or failed product reported")
        if "Delivery" in categories and self._contains_any(text, SERIOUS_DELIVERY_PHRASES):
            score += 2
            reasons.append("Serious delivery failure reported")
        if validation.requires_human_review and validation.validated_severity == "High":
            score += 1
            reasons.append("Validator requires human review for serious impact")

        risk_level = self._risk_level(score)
        recovery_required = risk_level in {
            RecoveryRiskLevel.HIGH,
            RecoveryRiskLevel.CRITICAL,
        }
        if not reasons:
            reasons.append("No configured recovery risk indicators detected")
        case = RecoveryCase(
            validation=validation,
            risk_level=risk_level.value,
            risk_score=score,
            recovery_required=recovery_required,
            status=(
                RecoveryStatus.OPEN.value if recovery_required else RecoveryStatus.DISMISSED.value
            ),
            suggested_action=(self._suggested_action(categories) if recovery_required else None),
            response_draft=None,
        )
        case.reasons.extend(RecoveryReason(reason=reason) for reason in reasons)
        self.session.add(case)
        self.session.commit()
        return get_recovery_case(self.session, case.id)

    def evaluate_all(self) -> RecoveryBatchSummary:
        validations = self.session.scalars(
            select(FeedbackValidation)
            .where(
                FeedbackValidation.validation_status.in_(TRUSTED_VALIDATION_STATUSES),
                ~FeedbackValidation.recovery_case.has(),
            )
            .options(
                selectinload(FeedbackValidation.analysis).selectinload(FeedbackAnalysis.feedback),
                selectinload(FeedbackValidation.categories),
            )
            .order_by(FeedbackValidation.id)
        ).all()
        summary = RecoveryBatchSummary(
            total=len(validations), evaluated=0, recovery_required=0, low_risk=0
        )
        for validation in validations:
            case = self.evaluate_validation(validation)
            summary.evaluated += 1
            summary.recovery_required += int(case.recovery_required)
            summary.low_risk += int(not case.recovery_required)
        return summary

    def _validations_for_external_id(
        self, external_feedback_id: str, source: str | None
    ) -> list[FeedbackValidation]:
        statement = (
            select(FeedbackValidation)
            .join(FeedbackValidation.analysis)
            .join(FeedbackAnalysis.feedback)
            .where(
                FeedbackAnalysis.analysis_status == "completed",
                FeedbackValidation.validation_status.in_(TRUSTED_VALIDATION_STATUSES),
                FeedbackAnalysis.feedback.has(feedback_id=external_feedback_id),
            )
            .options(
                selectinload(FeedbackValidation.analysis).selectinload(FeedbackAnalysis.feedback),
                selectinload(FeedbackValidation.categories),
            )
        )
        if source is not None:
            statement = statement.where(FeedbackAnalysis.feedback.has(source=source))
        return list(self.session.scalars(statement).all())

    def _risk_level(self, score: int) -> RecoveryRiskLevel:
        if score >= self.critical_score:
            return RecoveryRiskLevel.CRITICAL
        if score >= self.high_score:
            return RecoveryRiskLevel.HIGH
        if score >= 2:
            return RecoveryRiskLevel.MEDIUM
        return RecoveryRiskLevel.LOW

    @staticmethod
    def _suggested_action(categories: set[str]) -> str:
        if "Product Quality" in categories:
            return (
                "Manager review of the product or order and any appropriate replacement or "
                "refund options; customer contact requires human approval."
            )
        if "Delivery" in categories:
            return (
                "Priority review of the order and delivery history; customer contact requires "
                "human approval."
            )
        return (
            "Priority manager review to decide whether customer-service follow-up is appropriate."
        )

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()


def get_recovery_case_by_validation(session: Session, validation_id: int) -> RecoveryCase | None:
    return session.scalar(_case_query().where(RecoveryCase.validation_id == validation_id))


def get_recovery_case(session: Session, case_id: int) -> RecoveryCase | None:
    return session.scalar(_case_query().where(RecoveryCase.id == case_id))


def list_recovery_cases(
    session: Session,
    *,
    risk_level: str | None = None,
    status: str | None = None,
) -> list[RecoveryCase]:
    statement = _case_query()
    if risk_level is not None:
        statement = statement.where(RecoveryCase.risk_level == risk_level)
    if status is not None:
        statement = statement.where(RecoveryCase.status == status)
    return list(session.scalars(statement.order_by(RecoveryCase.id)).all())


def _case_query():
    return select(RecoveryCase).options(
        selectinload(RecoveryCase.reasons),
        selectinload(RecoveryCase.validation)
        .selectinload(FeedbackValidation.analysis)
        .selectinload(FeedbackAnalysis.feedback),
    )


def recovery_case_response(case: RecoveryCase) -> RecoveryCaseRead:
    feedback = case.validation.analysis.feedback
    return RecoveryCaseRead(
        id=case.id,
        feedback_db_id=feedback.id,
        feedback_id=feedback.feedback_id,
        risk_level=case.risk_level,
        risk_score=case.risk_score,
        recovery_required=case.recovery_required,
        status=case.status,
        reasons=case.reasons,
        suggested_action=case.suggested_action,
        response_draft=case.response_draft,
        assigned_to=case.assigned_to,
        created_at=case.created_at,
        updated_at=case.updated_at,
        resolved_at=case.resolved_at,
    )


def update_recovery_status(
    session: Session, case: RecoveryCase, update: RecoveryStatusUpdate
) -> RecoveryCase:
    case.status = update.status.value
    if "assigned_to" in update.model_fields_set:
        case.assigned_to = update.assigned_to
    if update.status == RecoveryStatus.RESOLVED:
        case.resolved_at = datetime.now(UTC).replace(tzinfo=None)
    else:
        case.resolved_at = None
    case.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.commit()
    return get_recovery_case(session, case.id)
