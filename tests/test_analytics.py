from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import create_session_factory
from backend.app.main import create_app
from backend.app.models import (
    Feedback,
    FeedbackAnalysis,
    FeedbackAspect,
    FeedbackValidation,
    ValidationCategory,
)
from backend.app.reference import load_reference_data


@pytest.fixture
def references():
    root = Path(__file__).resolve().parents[1]
    return load_reference_data(
        root / "data/reference/categories.json",
        root / "data/reference/business_rules.json",
    )


@pytest.fixture
def analytics_app(tmp_path, references):
    database_url = f"sqlite:///{tmp_path / 'analytics.db'}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        trend_min_feedback=3,
        spike_min_current_count=3,
        spike_percent_increase=50,
    )
    app = create_app(settings, reference_data=references)
    with TestClient(app) as client:
        engine, session_factory = create_session_factory(database_url)
        yield client, session_factory
        engine.dispose()


def seed(
    session_factory,
    feedback_id,
    *,
    sentiment="Negative",
    severity="Medium",
    categories=("Delivery",),
    validation_status="approved",
    requires_review=False,
    submitted_at="2026-09-08T10:00:00",
    source="survey",
    rating=None,
    classifier_sentiment=None,
    classifier_severity=None,
    classifier_categories=None,
):
    feedback = Feedback(
        feedback_id=feedback_id,
        source=source,
        submitted_at=datetime.fromisoformat(submitted_at) if submitted_at else None,
        rating=rating,
        feedback_text=f"Feedback text for {feedback_id}",
        processing_status="validated" if validation_status else "pending",
    )
    if validation_status is None:
        with session_factory() as session:
            session.add(feedback)
            session.commit()
        return

    raw_categories = classifier_categories or categories
    raw_sentiment = classifier_sentiment or ("Negative" if sentiment == "Mixed" else sentiment)
    raw_severity = classifier_severity or severity
    analysis = FeedbackAnalysis(
        feedback=feedback,
        primary_category=raw_categories[0],
        sentiment=raw_sentiment,
        severity=raw_severity,
        summary="Classifier summary.",
        is_mixed=sentiment == "Mixed",
        confidence=0.9,
        requires_review=False,
        analysis_status="completed",
        model_used="fake-classifier",
    )
    analysis.aspects.extend(
        FeedbackAspect(
            category=category,
            sentiment=raw_sentiment,
            severity=raw_severity,
            evidence_text="Feedback text",
        )
        for category in raw_categories
    )
    validation = FeedbackValidation(
        analysis=analysis,
        validation_status=validation_status,
        overall_confidence=0.9,
        requires_human_review=requires_review,
        validated_sentiment=sentiment,
        validated_severity=severity,
        validation_summary="Validation summary.",
        model_used="fake-validator",
    )
    validation.categories.extend(ValidationCategory(category=category) for category in categories)
    with session_factory() as session:
        session.add(feedback)
        session.commit()


def category(response, name):
    return next(item for item in response["categories"] if item["category"] == name)


def pattern(response, group, name):
    return next(item for item in response[group] if item["category"] == name)


def test_sentiment_counts(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", sentiment="Positive")
    seed(sessions, "F2", sentiment="Neutral")
    seed(sessions, "F3", sentiment="Negative")
    seed(sessions, "F4", sentiment="Mixed")
    result = client.get("/api/analytics/sentiment").json()
    assert (result["total"], result["positive"], result["neutral"]) == (4, 1, 1)
    assert (result["negative"], result["mixed"]) == (1, 1)


def test_sentiment_percentages(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", sentiment="Positive")
    seed(sessions, "F2", sentiment="Positive")
    seed(sessions, "F3", sentiment="Negative")
    result = client.get("/api/analytics/sentiment").json()
    assert result["positive_percentage"] == 66.67
    assert result["negative_percentage"] == 33.33
    assert result["neutral_percentage"] == 0.0


def test_zero_feedback_handling(analytics_app):
    client, _ = analytics_app
    result = client.get("/api/analytics/sentiment").json()
    assert result == {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
        "mixed": 0,
        "total": 0,
        "positive_percentage": 0.0,
        "neutral_percentage": 0.0,
        "negative_percentage": 0.0,
        "mixed_percentage": 0.0,
    }


def test_category_counts_include_all_approved_categories(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", categories=("Delivery",))
    seed(sessions, "F2", categories=("Delivery",))
    result = client.get("/api/analytics/categories").json()
    assert len(result["categories"]) == 9
    assert category(result, "Delivery")["feedback_count"] == 2
    assert category(result, "Pricing")["feedback_count"] == 0


def test_multi_aspect_feedback_distinguishes_records_and_aspects(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", categories=("Delivery", "Customer Service"))
    result = client.get("/api/analytics/categories").json()
    assert result["trusted_feedback_count"] == 1
    assert result["total_aspect_count"] == 2
    assert category(result, "Delivery")["feedback_count"] == 1
    assert category(result, "Customer Service")["feedback_count"] == 1


def test_duplicate_classifier_aspects_do_not_inflate_trend_count(analytics_app):
    client, sessions = analytics_app
    seed(
        sessions,
        "F1",
        categories=("Delivery",),
        classifier_categories=("Delivery", "Delivery"),
    )
    result = client.get("/api/analytics/trends").json()
    delivery = pattern(result, "negative_patterns", "Delivery")
    assert delivery["feedback_count"] == 1
    assert delivery["supporting_feedback_ids"] == ["F1"]


def test_recurring_trend_below_default_threshold(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1")
    seed(sessions, "F2")
    result = client.get("/api/analytics/trends").json()
    assert pattern(result, "negative_patterns", "Delivery")["recurring"] is False


def test_recurring_trend_at_default_threshold(analytics_app):
    client, sessions = analytics_app
    for number in range(1, 4):
        seed(sessions, f"F{number}")
    result = client.get("/api/analytics/trends").json()
    delivery = pattern(result, "negative_patterns", "Delivery")
    assert delivery["recurring"] is True
    assert delivery["supporting_feedback_ids"] == ["F1", "F2", "F3"]


def test_positive_recurring_pattern(analytics_app):
    client, sessions = analytics_app
    for number in range(1, 4):
        seed(
            sessions,
            f"F{number}",
            sentiment="Positive",
            severity="Low",
            categories=("Staff Behaviour",),
        )
    result = client.get("/api/analytics/trends").json()
    staff = pattern(result, "positive_patterns", "Staff Behaviour")
    assert staff["recurring"] is True
    assert staff["sentiment"] == "Positive"


def test_severity_metrics(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", severity="Low", sentiment="Positive")
    seed(sessions, "F2", severity="Medium")
    seed(sessions, "F3", severity="High")
    result = client.get("/api/analytics/severity").json()
    assert (result["low"], result["medium"], result["high"]) == (1, 1, 1)
    assert result["high_severity_negative"] == 1
    assert (
        next(
            item["count"]
            for item in result["high_severity_by_category"]
            if item["category"] == "Delivery"
        )
        == 1
    )


def test_needs_review_validation_is_excluded(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", validation_status="needs_review", requires_review=True)
    result = client.get("/api/analytics/sentiment").json()
    assert result["total"] == 0


def test_rejected_validation_is_excluded(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", validation_status="rejected", requires_review=True)
    result = client.get("/api/analytics/categories").json()
    assert result["trusted_feedback_count"] == 0


def test_approved_with_changes_uses_validated_values(analytics_app):
    client, sessions = analytics_app
    seed(
        sessions,
        "F1",
        sentiment="Neutral",
        severity="Low",
        categories=("Pricing",),
        validation_status="approved_with_changes",
        requires_review=True,
        classifier_sentiment="Negative",
        classifier_severity="High",
        classifier_categories=("Delivery",),
    )
    sentiments = client.get("/api/analytics/sentiment").json()
    categories = client.get("/api/analytics/categories").json()
    severities = client.get("/api/analytics/severity").json()
    assert sentiments["neutral"] == 1 and sentiments["negative"] == 0
    assert category(categories, "Pricing")["feedback_count"] == 1
    assert category(categories, "Delivery")["feedback_count"] == 0
    assert severities["low"] == 1 and severities["high"] == 0


def test_daily_timeline(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", submitted_at="2026-09-08T09:00:00")
    seed(
        sessions,
        "F2",
        sentiment="Positive",
        submitted_at="2026-09-08T15:00:00",
    )
    seed(sessions, "F3", submitted_at="2026-09-09T09:00:00")
    points = client.get("/api/analytics/timeline?period=daily").json()["points"]
    assert [point["period_start"] for point in points] == ["2026-09-08", "2026-09-09"]
    assert points[0]["total"] == 2
    assert (points[0]["positive"], points[0]["negative"]) == (1, 1)


def test_weekly_timeline_uses_monday_start(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", submitted_at="2026-09-08T09:00:00")
    seed(sessions, "F2", submitted_at="2026-09-13T09:00:00")
    seed(sessions, "F3", submitted_at="2026-09-14T09:00:00")
    points = client.get("/api/analytics/timeline?period=weekly").json()["points"]
    assert [point["period_start"] for point in points] == ["2026-09-07", "2026-09-14"]
    assert [point["total"] for point in points] == [2, 1]


def test_spike_detection(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "P1", submitted_at="2026-09-01T09:00:00")
    seed(sessions, "P2", submitted_at="2026-09-02T09:00:00")
    for number in range(1, 4):
        seed(sessions, f"C{number}", submitted_at=f"2026-09-{7 + number:02d}T09:00:00")
    result = client.get("/api/analytics/emerging-issues?period=weekly&as_of=2026-09-09").json()
    issue = next(item for item in result["issues"] if item["category"] == "Delivery")
    assert issue["status"] == "spike"
    assert (issue["previous_count"], issue["current_count"]) == (2, 3)
    assert issue["percentage_change"] == 50.0


def test_no_spike_below_minimum_volume(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "P1", submitted_at="2026-09-01T09:00:00")
    seed(sessions, "C1", submitted_at="2026-09-08T09:00:00")
    seed(sessions, "C2", submitted_at="2026-09-09T09:00:00")
    result = client.get("/api/analytics/emerging-issues?period=weekly&as_of=2026-09-09").json()
    assert result["issues"] == []


def test_previous_zero_creates_new_emerging_issue(analytics_app):
    client, sessions = analytics_app
    seed(
        sessions,
        "P1",
        sentiment="Positive",
        categories=("Staff Behaviour",),
        submitted_at="2026-09-01T09:00:00",
    )
    for number in range(1, 4):
        seed(
            sessions,
            f"C{number}",
            categories=("Website / App",),
            submitted_at=f"2026-09-{7 + number:02d}T09:00:00",
        )
    result = client.get("/api/analytics/emerging-issues?period=weekly&as_of=2026-09-09").json()
    issue = next(item for item in result["issues"] if item["category"] == "Website / App")
    assert issue["status"] == "new_emerging_issue"
    assert issue["previous_count"] == 0
    assert issue["percentage_change"] is None


def test_filtering_by_dates(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", submitted_at="2026-09-01T09:00:00")
    seed(sessions, "F2", submitted_at="2026-09-10T09:00:00")
    seed(sessions, "F3", submitted_at=None)
    result = client.get("/api/analytics/sentiment?start_date=2026-09-05&end_date=2026-09-12").json()
    assert result["total"] == 1


def test_filtering_by_source(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", source="google_forms")
    seed(sessions, "F2", source="email")
    result = client.get("/api/analytics/sentiment?source=google_forms").json()
    assert result["total"] == 1


def test_overview_counts_average_rating_and_review_queue(analytics_app):
    client, sessions = analytics_app
    seed(sessions, "F1", sentiment="Positive", rating=4, source="store")
    seed(sessions, "F2", rating=2, source="online")
    seed(
        sessions,
        "F3",
        validation_status="needs_review",
        requires_review=True,
        rating=1,
    )
    seed(sessions, "F4", validation_status=None)
    result = client.get("/api/analytics/overview").json()
    assert result["total_feedback_count"] == 4
    assert result["trusted_validated_feedback_count"] == 2
    assert result["records_requiring_human_review"] == 1
    assert result["rated_feedback_count"] == 2
    assert result["average_rating"] == 3.0
    assert {item["source"] for item in result["source_counts"]} == {"online", "store"}
