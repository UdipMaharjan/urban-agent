import hashlib
import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..agents.recommender import RecommendationAgent
from ..models import (
    BusinessRecommendation,
    Feedback,
    FeedbackAnalysis,
    FeedbackValidation,
    RecommendationApprovalEvent,
    RecommendationEvidence,
)
from ..reference import ReferenceData
from ..schemas import (
    BusinessRecommendationRead,
    RecommendationApprovalEventRead,
    RecommendationBusinessContext,
    RecommendationDecision,
    RecommendationEvidenceSummary,
    RecommendationGenerationError,
    RecommendationGenerationSummary,
    RecommendationResult,
    RecommendationTrendInput,
    TimelinePeriod,
)
from .analytics import TRUSTED_VALIDATION_STATUSES, AnalyticsFilters, AnalyticsService
from .llm import LLMServiceError


class RecommendationService:
    def __init__(
        self,
        session: Session,
        analytics: AnalyticsService,
        references: ReferenceData,
    ):
        self.session = session
        self.analytics = analytics
        self.references = references

    def trend_inputs(
        self,
        filters: AnalyticsFilters,
        *,
        period: TimelinePeriod = TimelinePeriod.WEEKLY,
        as_of: date | None = None,
    ) -> list[RecommendationTrendInput]:
        trends = self.analytics.trends(filters)
        emerging = self.analytics.emerging_issues(filters, period, as_of)
        negative_by_category = {
            pattern.category: pattern for pattern in trends.negative_patterns if pattern.recurring
        }
        emerging_by_category = {issue.category: issue for issue in emerging.issues}
        eligible_categories = [
            category
            for category in self.analytics.category_names
            if category in negative_by_category or category in emerging_by_category
        ]
        trusted_records = self.analytics.trusted_records(filters)
        validations = self._trusted_validations()
        inputs = []
        for category in eligible_categories:
            supporting_ids = set()
            if category in negative_by_category:
                supporting_ids.update(negative_by_category[category].supporting_feedback_ids)
            if category in emerging_by_category:
                supporting_ids.update(emerging_by_category[category].supporting_feedback_ids)
            ordered_ids = sorted(supporting_ids)
            evidence = self._evidence_summaries(validations, category, ordered_ids)
            high_severity_count = sum(
                record.feedback_id in supporting_ids
                and record.severity == "High"
                and category in record.categories
                for record in trusted_records
            )
            inputs.append(
                RecommendationTrendInput(
                    category=category,
                    feedback_count=len(ordered_ids),
                    negative_count=len(ordered_ids),
                    high_severity_count=high_severity_count,
                    supporting_feedback_ids=ordered_ids,
                    supporting_evidence=evidence,
                    business_context=RecommendationBusinessContext(
                        relevant_rules=[
                            rule.rule
                            for rule in self.references.business_rules.rules
                            if rule.category == category
                        ],
                        management_preference=(self.references.business_rules.improvement_approach),
                        decision_authority=self.references.business_rules.decision_authority,
                    ),
                    emerging_issue_status=(
                        emerging_by_category[category].status
                        if category in emerging_by_category
                        else None
                    ),
                )
            )
        return inputs

    def generate(
        self,
        agent: RecommendationAgent,
        filters: AnalyticsFilters,
        *,
        period: TimelinePeriod = TimelinePeriod.WEEKLY,
        as_of: date | None = None,
        trend_inputs: list[RecommendationTrendInput] | None = None,
    ) -> RecommendationGenerationSummary:
        if trend_inputs is None:
            trend_inputs = self.trend_inputs(filters, period=period, as_of=as_of)
        summary = RecommendationGenerationSummary(
            eligible_trends=len(trend_inputs),
            generated=0,
            skipped_duplicates=0,
            failed=0,
        )
        for trend in trend_inputs:
            fingerprint = self._fingerprint(trend)
            existing = self.session.scalar(
                select(BusinessRecommendation).where(
                    BusinessRecommendation.trend_fingerprint == fingerprint
                )
            )
            if existing is not None:
                summary.skipped_duplicates += 1
                continue
            try:
                result = agent.recommend(trend)
                recommendation = self._save(result, trend, fingerprint, agent.llm.model)
                summary.generated += 1
                summary.recommendations.append(recommendation_response(recommendation))
            except LLMServiceError as exc:
                self.session.rollback()
                summary.failed += 1
                summary.errors.append(
                    RecommendationGenerationError(
                        category=trend.category,
                        message=str(exc),
                    )
                )
        return summary

    def _save(
        self,
        result: RecommendationResult,
        trend: RecommendationTrendInput,
        fingerprint: str,
        model_used: str,
    ) -> BusinessRecommendation:
        feedback_by_external_id = {
            feedback.feedback_id: feedback
            for feedback in self.session.scalars(
                select(Feedback).where(Feedback.feedback_id.in_(trend.supporting_feedback_ids))
            ).all()
        }
        if set(feedback_by_external_id) != set(trend.supporting_feedback_ids):
            raise RuntimeError("A supporting feedback record is no longer available.")
        recommendation = BusinessRecommendation(
            category=result.category,
            priority=result.priority.value,
            problem_summary=result.problem_summary,
            recommendation=result.recommendation,
            business_rationale=result.business_rationale,
            evidence_count=result.evidence_count,
            requires_management_approval=True,
            approval_status="pending",
            confidence=result.confidence,
            trend_fingerprint=fingerprint,
            model_used=model_used,
        )
        recommendation.evidence.extend(
            RecommendationEvidence(feedback=feedback_by_external_id[feedback_id])
            for feedback_id in result.supporting_feedback_ids
        )
        self.session.add(recommendation)
        self.session.commit()
        return get_recommendation(self.session, recommendation.id)

    def _trusted_validations(self) -> list[FeedbackValidation]:
        return list(
            self.session.scalars(
                select(FeedbackValidation)
                .where(FeedbackValidation.validation_status.in_(TRUSTED_VALIDATION_STATUSES))
                .options(
                    selectinload(FeedbackValidation.analysis).selectinload(
                        FeedbackAnalysis.feedback
                    ),
                    selectinload(FeedbackValidation.categories),
                )
            ).all()
        )

    @staticmethod
    def _evidence_summaries(
        validations: list[FeedbackValidation], category: str, feedback_ids: list[str]
    ) -> list[RecommendationEvidenceSummary]:
        wanted = set(feedback_ids)
        by_id = {}
        for validation in validations:
            feedback_id = validation.analysis.feedback.feedback_id
            categories = {item.category for item in validation.categories}
            if feedback_id in wanted and category in categories and feedback_id not in by_id:
                by_id[feedback_id] = RecommendationEvidenceSummary(
                    feedback_id=feedback_id,
                    analysis_summary=validation.analysis.summary,
                    validation_summary=validation.validation_summary,
                    validated_severity=validation.validated_severity,
                )
        return [by_id[feedback_id] for feedback_id in feedback_ids]

    @staticmethod
    def _fingerprint(trend: RecommendationTrendInput) -> str:
        return hashlib.sha256(
            json.dumps(
                trend.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()


def get_recommendation(session: Session, recommendation_id: int) -> BusinessRecommendation | None:
    return session.scalar(
        select(BusinessRecommendation)
        .where(BusinessRecommendation.id == recommendation_id)
        .options(
            selectinload(BusinessRecommendation.evidence).selectinload(
                RecommendationEvidence.feedback
            ),
            selectinload(BusinessRecommendation.approval_events),
        )
    )


def list_recommendations(
    session: Session,
    *,
    priority: str | None = None,
    category: str | None = None,
    approval_status: str | None = None,
) -> list[BusinessRecommendation]:
    statement = select(BusinessRecommendation).options(
        selectinload(BusinessRecommendation.evidence).selectinload(RecommendationEvidence.feedback),
        selectinload(BusinessRecommendation.approval_events),
    )
    if priority is not None:
        statement = statement.where(BusinessRecommendation.priority == priority)
    if category is not None:
        statement = statement.where(BusinessRecommendation.category == category)
    if approval_status is not None:
        statement = statement.where(BusinessRecommendation.approval_status == approval_status)
    return list(session.scalars(statement.order_by(BusinessRecommendation.id)).all())


def recommendation_response(
    recommendation: BusinessRecommendation,
) -> BusinessRecommendationRead:
    return BusinessRecommendationRead(
        id=recommendation.id,
        category=recommendation.category,
        priority=recommendation.priority,
        problem_summary=recommendation.problem_summary,
        recommendation=recommendation.recommendation,
        business_rationale=recommendation.business_rationale,
        evidence_count=recommendation.evidence_count,
        supporting_feedback_ids=[item.feedback.feedback_id for item in recommendation.evidence],
        requires_management_approval=recommendation.requires_management_approval,
        approval_status=recommendation.approval_status,
        confidence=recommendation.confidence,
        model_used=recommendation.model_used,
        created_at=recommendation.created_at,
        updated_at=recommendation.updated_at,
        approval_history=[
            RecommendationApprovalEventRead.model_validate(event)
            for event in recommendation.approval_events
        ],
    )


def decide_recommendation(
    session: Session,
    recommendation: BusinessRecommendation,
    decision: RecommendationDecision,
) -> BusinessRecommendation:
    recommendation.approval_status = decision.value
    recommendation.updated_at = datetime.now(UTC).replace(tzinfo=None)
    recommendation.approval_events.append(RecommendationApprovalEvent(decision=decision.value))
    session.commit()
    return get_recommendation(session, recommendation.id)
