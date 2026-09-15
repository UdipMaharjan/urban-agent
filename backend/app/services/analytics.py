from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Feedback, FeedbackAnalysis, FeedbackValidation
from ..schemas import (
    AnalyticsOverview,
    CategoryAnalytics,
    CategoryAnalyticsItem,
    CategoryCount,
    EmergingIssue,
    EmergingIssuesAnalytics,
    PatternItem,
    SentimentAnalytics,
    SentimentBreakdown,
    SeverityAnalytics,
    SeverityBreakdown,
    SourceCount,
    TimelineAnalytics,
    TimelinePeriod,
    TimelinePoint,
    TrendAnalytics,
)

TRUSTED_VALIDATION_STATUSES = {"approved", "approved_with_changes"}


@dataclass(frozen=True)
class AnalyticsFilters:
    start_date: date | None = None
    end_date: date | None = None
    source: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class TrustedFeedback:
    database_id: int
    feedback_id: str
    source: str
    submitted_date: date | None
    rating: float | None
    sentiment: str
    severity: str
    categories: tuple[str, ...]


class AnalyticsService:
    """Calculates trusted analytics with deterministic Python and SQLAlchemy."""

    def __init__(
        self,
        session: Session,
        category_names: list[str],
        *,
        trend_min_feedback: int,
        spike_min_current_count: int,
        spike_percent_increase: float,
    ):
        self.session = session
        self.category_names = category_names
        self.trend_min_feedback = trend_min_feedback
        self.spike_min_current_count = spike_min_current_count
        self.spike_percent_increase = spike_percent_increase

    def overview(self, filters: AnalyticsFilters) -> AnalyticsOverview:
        records = self.trusted_records(filters)
        all_validations = self._validations()
        total_feedback = self._total_feedback_count(filters, all_validations)
        review_count = sum(
            validation.requires_human_review
            for validation in all_validations
            if self._validation_matches(validation, filters)
        )
        ratings = [record.rating for record in records if record.rating is not None]
        source_counts = Counter(record.source for record in records)
        trends = self.trends(filters)
        return AnalyticsOverview(
            total_feedback_count=total_feedback,
            trusted_validated_feedback_count=len(records),
            records_requiring_human_review=review_count,
            rated_feedback_count=len(ratings),
            average_rating=round(sum(ratings) / len(ratings), 2) if ratings else None,
            total_aspect_count=sum(len(record.categories) for record in records),
            source_counts=[
                SourceCount(
                    source=source,
                    count=count,
                    percentage=self._percentage(count, len(records)),
                )
                for source, count in sorted(source_counts.items())
            ],
            recurring_negative_trend_count=sum(
                pattern.recurring for pattern in trends.negative_patterns
            ),
            recurring_positive_pattern_count=sum(
                pattern.recurring for pattern in trends.positive_patterns
            ),
        )

    def sentiment(self, filters: AnalyticsFilters) -> SentimentAnalytics:
        records = self.trusted_records(filters)
        counts = Counter(record.sentiment for record in records)
        total = len(records)
        return SentimentAnalytics(
            total=total,
            positive=counts["Positive"],
            neutral=counts["Neutral"],
            negative=counts["Negative"],
            mixed=counts["Mixed"],
            positive_percentage=self._percentage(counts["Positive"], total),
            neutral_percentage=self._percentage(counts["Neutral"], total),
            negative_percentage=self._percentage(counts["Negative"], total),
            mixed_percentage=self._percentage(counts["Mixed"], total),
        )

    def categories(self, filters: AnalyticsFilters) -> CategoryAnalytics:
        records = self.trusted_records(filters)
        total_aspects = sum(len(record.categories) for record in records)
        items = []
        for category in self.category_names:
            supporting = [record for record in records if category in record.categories]
            sentiment_counts = Counter(record.sentiment for record in supporting)
            severity_counts = Counter(record.severity for record in supporting)
            count = len(supporting)
            items.append(
                CategoryAnalyticsItem(
                    category=category,
                    feedback_count=count,
                    aspect_count=count,
                    percentage=self._percentage(count, len(records)),
                    aspect_percentage=self._percentage(count, total_aspects),
                    sentiment_counts=self._sentiment_breakdown(sentiment_counts),
                    severity_counts=self._severity_breakdown(severity_counts),
                )
            )
        return CategoryAnalytics(
            trusted_feedback_count=len(records),
            total_aspect_count=total_aspects,
            categories=items,
        )

    def severity(self, filters: AnalyticsFilters) -> SeverityAnalytics:
        records = self.trusted_records(filters)
        counts = Counter(record.severity for record in records)
        high_negative = sum(
            record.severity == "High" and record.sentiment == "Negative" for record in records
        )
        return SeverityAnalytics(
            total=len(records),
            low=counts["Low"],
            medium=counts["Medium"],
            high=counts["High"],
            high_severity_negative=high_negative,
            high_severity_by_category=[
                CategoryCount(
                    category=category,
                    count=sum(
                        record.severity == "High" and category in record.categories
                        for record in records
                    ),
                )
                for category in self.category_names
            ],
        )

    def trends(self, filters: AnalyticsFilters) -> TrendAnalytics:
        records = self.trusted_records(filters)
        return TrendAnalytics(
            threshold=self.trend_min_feedback,
            negative_patterns=self._patterns(records, "Negative"),
            positive_patterns=self._patterns(records, "Positive"),
        )

    def timeline(self, filters: AnalyticsFilters, period: TimelinePeriod) -> TimelineAnalytics:
        groups: dict[date, list[TrustedFeedback]] = defaultdict(list)
        for record in self.trusted_records(filters):
            if record.submitted_date is not None:
                groups[self._period_start(record.submitted_date, period)].append(record)

        points = []
        for period_start in sorted(groups):
            records = groups[period_start]
            sentiments = Counter(record.sentiment for record in records)
            category_counts = Counter(
                category for record in records for category in record.categories
            )
            points.append(
                TimelinePoint(
                    period_start=period_start,
                    total=len(records),
                    positive=sentiments["Positive"],
                    neutral=sentiments["Neutral"],
                    negative=sentiments["Negative"],
                    mixed=sentiments["Mixed"],
                    category_counts=[
                        CategoryCount(category=category, count=category_counts[category])
                        for category in self.category_names
                    ],
                )
            )
        return TimelineAnalytics(period=period, points=points)

    def emerging_issues(
        self,
        filters: AnalyticsFilters,
        period: TimelinePeriod,
        as_of: date | None = None,
    ) -> EmergingIssuesAnalytics:
        records = [
            record for record in self.trusted_records(filters) if record.submitted_date is not None
        ]
        if as_of is None and records:
            as_of = max(record.submitted_date for record in records)
        if as_of is None:
            return EmergingIssuesAnalytics(
                period=period,
                current_period_start=None,
                previous_period_start=None,
                minimum_current_count=self.spike_min_current_count,
                percentage_increase_threshold=self.spike_percent_increase,
                issues=[],
            )

        current_start = self._period_start(as_of, period)
        period_length = timedelta(days=1 if period == TimelinePeriod.DAILY else 7)
        previous_start = current_start - period_length
        previous_available = any(
            self._period_start(record.submitted_date, period) == previous_start
            for record in records
        )
        issues = []
        if previous_available:
            for category in self.category_names:
                previous_ids = self._negative_ids_for_period(
                    records, category, period, previous_start
                )
                current_ids = self._negative_ids_for_period(
                    records, category, period, current_start
                )
                current_count = len(current_ids)
                previous_count = len(previous_ids)
                if current_count < self.spike_min_current_count:
                    continue
                if previous_count == 0:
                    issues.append(
                        EmergingIssue(
                            category=category,
                            status="new_emerging_issue",
                            previous_count=0,
                            current_count=current_count,
                            percentage_change=None,
                            supporting_feedback_ids=current_ids,
                        )
                    )
                    continue
                percentage_change = round(
                    ((current_count - previous_count) / previous_count) * 100, 2
                )
                if percentage_change >= self.spike_percent_increase:
                    issues.append(
                        EmergingIssue(
                            category=category,
                            status="spike",
                            previous_count=previous_count,
                            current_count=current_count,
                            percentage_change=percentage_change,
                            supporting_feedback_ids=current_ids,
                        )
                    )
        return EmergingIssuesAnalytics(
            period=period,
            current_period_start=current_start,
            previous_period_start=previous_start,
            minimum_current_count=self.spike_min_current_count,
            percentage_increase_threshold=self.spike_percent_increase,
            issues=issues,
        )

    def trusted_records(self, filters: AnalyticsFilters) -> list[TrustedFeedback]:
        records = []
        for validation in self._validations():
            if validation.validation_status not in TRUSTED_VALIDATION_STATUSES:
                continue
            if not self._validation_matches(validation, filters):
                continue
            feedback = validation.analysis.feedback
            records.append(
                TrustedFeedback(
                    database_id=feedback.id,
                    feedback_id=feedback.feedback_id,
                    source=feedback.source,
                    submitted_date=(
                        feedback.submitted_at.date() if feedback.submitted_at else None
                    ),
                    rating=feedback.rating,
                    sentiment=validation.validated_sentiment,
                    severity=validation.validated_severity,
                    categories=tuple(category.category for category in validation.categories),
                )
            )
        return records

    def _validations(self) -> list[FeedbackValidation]:
        return list(
            self.session.scalars(
                select(FeedbackValidation)
                .options(
                    selectinload(FeedbackValidation.analysis).selectinload(
                        FeedbackAnalysis.feedback
                    ),
                    selectinload(FeedbackValidation.categories),
                )
                .order_by(FeedbackValidation.id)
            ).all()
        )

    def _total_feedback_count(
        self, filters: AnalyticsFilters, validations: list[FeedbackValidation]
    ) -> int:
        category_feedback_ids = None
        if filters.category is not None:
            category_feedback_ids = {
                validation.analysis.feedback_id
                for validation in validations
                if filters.category in {category.category for category in validation.categories}
            }
        return sum(
            self._feedback_matches(feedback, filters, category_feedback_ids)
            for feedback in self.session.scalars(select(Feedback)).all()
        )

    def _validation_matches(
        self, validation: FeedbackValidation, filters: AnalyticsFilters
    ) -> bool:
        feedback = validation.analysis.feedback
        if not self._feedback_matches(feedback, filters):
            return False
        return filters.category is None or filters.category in {
            category.category for category in validation.categories
        }

    @staticmethod
    def _feedback_matches(
        feedback: Feedback,
        filters: AnalyticsFilters,
        category_feedback_ids: set[int] | None = None,
    ) -> bool:
        if filters.source is not None and feedback.source != filters.source:
            return False
        submitted_date = feedback.submitted_at.date() if feedback.submitted_at else None
        if filters.start_date is not None and (
            submitted_date is None or submitted_date < filters.start_date
        ):
            return False
        if filters.end_date is not None and (
            submitted_date is None or submitted_date > filters.end_date
        ):
            return False
        return category_feedback_ids is None or feedback.id in category_feedback_ids

    def _patterns(self, records: list[TrustedFeedback], sentiment: str) -> list[PatternItem]:
        patterns = []
        for category in self.category_names:
            feedback_ids = sorted(
                {
                    record.feedback_id
                    for record in records
                    if record.sentiment == sentiment and category in record.categories
                }
            )
            if feedback_ids:
                patterns.append(
                    PatternItem(
                        category=category,
                        sentiment=sentiment,
                        feedback_count=len(feedback_ids),
                        recurring=len(feedback_ids) >= self.trend_min_feedback,
                        supporting_feedback_ids=feedback_ids,
                    )
                )
        return patterns

    @staticmethod
    def _negative_ids_for_period(
        records: list[TrustedFeedback],
        category: str,
        period: TimelinePeriod,
        period_start: date,
    ) -> list[str]:
        return sorted(
            {
                record.feedback_id
                for record in records
                if record.sentiment == "Negative"
                and category in record.categories
                and AnalyticsService._period_start(record.submitted_date, period) == period_start
            }
        )

    @staticmethod
    def _period_start(value: date, period: TimelinePeriod) -> date:
        if period == TimelinePeriod.DAILY:
            return value
        return value - timedelta(days=value.weekday())

    @staticmethod
    def _percentage(count: int, total: int) -> float:
        return round((count / total) * 100, 2) if total else 0.0

    @staticmethod
    def _sentiment_breakdown(counts: Counter) -> SentimentBreakdown:
        return SentimentBreakdown(
            positive=counts["Positive"],
            neutral=counts["Neutral"],
            negative=counts["Negative"],
            mixed=counts["Mixed"],
        )

    @staticmethod
    def _severity_breakdown(counts: Counter) -> SeverityBreakdown:
        return SeverityBreakdown(low=counts["Low"], medium=counts["Medium"], high=counts["High"])
