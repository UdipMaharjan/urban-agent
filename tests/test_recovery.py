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
def recovery_app(tmp_path):
    root = Path(__file__).resolve().parents[1]
    references = load_reference_data(
        root / "data/reference/categories.json",
        root / "data/reference/business_rules.json",
    )
    database_url = f"sqlite:///{tmp_path / 'recovery.db'}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        recovery_high_score=5,
        recovery_critical_score=9,
    )
    with TestClient(create_app(settings, reference_data=references)) as client:
        engine, sessions = create_session_factory(database_url)
        yield client, sessions
        engine.dispose()


def seed_feedback(
    sessions,
    feedback_id,
    text,
    *,
    sentiment="Negative",
    severity="Low",
    categories=("Customer Service",),
    validation_status="approved",
    requires_review=False,
):
    feedback = Feedback(
        feedback_id=feedback_id,
        source="survey",
        feedback_text=text,
        processing_status="validated" if validation_status else "classified",
    )
    analysis = FeedbackAnalysis(
        feedback=feedback,
        primary_category=categories[0],
        sentiment=sentiment,
        severity=severity,
        summary="Classifier summary.",
        is_mixed=sentiment == "Mixed",
        confidence=0.9,
        requires_review=requires_review,
        analysis_status="completed",
        model_used="fake-classifier",
    )
    analysis.aspects.extend(
        FeedbackAspect(
            category=category,
            sentiment="Negative" if sentiment == "Mixed" else sentiment,
            severity=severity,
            evidence_text=text,
        )
        for category in categories
    )
    if validation_status is not None:
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
        validation.categories.extend(
            ValidationCategory(category=category) for category in categories
        )
    with sessions() as session:
        session.add(feedback)
        session.commit()


def test_high_severity_creates_recovery_case(recovery_app):
    client, sessions = recovery_app
    seed_feedback(
        sessions,
        "F004",
        "I received the wrong product and had to contact support twice before getting help.",
        severity="High",
        categories=("Product Quality", "Customer Service"),
    )
    case = client.post("/api/recovery/evaluate/F004").json()
    assert case["recovery_required"] is True
    assert case["risk_level"] in {"High", "Critical"}
    assert case["status"] == "open"


def test_low_risk_feedback_is_not_urgent(recovery_app):
    client, sessions = recovery_app
    seed_feedback(
        sessions,
        "F024",
        "Excellent support team. They responded within minutes.",
        sentiment="Positive",
        severity="Low",
    )
    case = client.post("/api/recovery/evaluate/F024").json()
    assert case["risk_level"] == "Low"
    assert case["recovery_required"] is False
    assert case["status"] == "dismissed"
    assert case["suggested_action"] is None


def test_repeated_failure_language_increases_risk(recovery_app):
    client, sessions = recovery_app
    seed_feedback(
        sessions,
        "F1",
        "The support response was disappointing.",
        sentiment="Positive",
    )
    seed_feedback(
        sessions,
        "F2",
        "I contacted support twice and the issue happened again.",
        sentiment="Positive",
    )
    baseline = client.post("/api/recovery/evaluate/F1").json()
    repeated = client.post("/api/recovery/evaluate/F2").json()
    assert repeated["risk_score"] > baseline["risk_score"]
    assert any("repeated" in reason["reason"].lower() for reason in repeated["reasons"])


def test_multiple_categories_increase_risk_score(recovery_app):
    client, sessions = recovery_app
    seed_feedback(sessions, "F1", "A negative service experience.")
    seed_feedback(
        sessions,
        "F2",
        "A negative service and delivery experience.",
        categories=("Customer Service", "Delivery"),
    )
    single = client.post("/api/recovery/evaluate/F1").json()
    multiple = client.post("/api/recovery/evaluate/F2").json()
    assert multiple["risk_score"] == single["risk_score"] + 1


def test_recovery_reasons_are_preserved(recovery_app):
    client, sessions = recovery_app
    seed_feedback(
        sessions,
        "F004",
        "I received the wrong product and contacted support twice.",
        severity="High",
        categories=("Product Quality", "Customer Service"),
    )
    case = client.post("/api/recovery/evaluate/F004").json()
    reasons = {item["reason"] for item in case["reasons"]}
    assert "Wrong product received" in reasons
    assert "Feedback describes repeated failure or contact" in reasons
    retrieved = client.get(f"/api/recovery/cases/{case['id']}").json()
    assert retrieved["reasons"] == case["reasons"]


def test_duplicate_recovery_evaluation_returns_existing_case(recovery_app):
    client, sessions = recovery_app
    seed_feedback(sessions, "F1", "A serious complaint.", severity="High")
    first = client.post("/api/recovery/evaluate/F1").json()
    second = client.post("/api/recovery/evaluate/F1").json()
    assert second["id"] == first["id"]
    assert len(client.get("/api/recovery/cases").json()) == 1


def test_batch_recovery_evaluation(recovery_app):
    client, sessions = recovery_app
    seed_feedback(sessions, "F1", "A serious complaint.", severity="High")
    seed_feedback(
        sessions,
        "F2",
        "Excellent support.",
        sentiment="Positive",
        severity="Low",
    )
    result = client.post("/api/recovery/evaluate-all").json()
    assert result == {"total": 2, "evaluated": 2, "recovery_required": 1, "low_risk": 1}
    assert client.post("/api/recovery/evaluate-all").json()["total"] == 0


def test_recovery_status_updates_are_human_controlled(recovery_app):
    client, sessions = recovery_app
    seed_feedback(sessions, "F1", "A serious complaint.", severity="High")
    case = client.post("/api/recovery/evaluate/F1").json()
    reviewing = client.patch(
        f"/api/recovery/cases/{case['id']}/status",
        json={"status": "under_review", "assigned_to": "Store manager"},
    ).json()
    assert reviewing["status"] == "under_review"
    assert reviewing["assigned_to"] == "Store manager"
    resolved = client.patch(
        f"/api/recovery/cases/{case['id']}/status",
        json={"status": "resolved"},
    ).json()
    assert resolved["resolved_at"] is not None


def test_unvalidated_feedback_is_not_trusted_for_recovery(recovery_app):
    client, sessions = recovery_app
    seed_feedback(
        sessions,
        "F1",
        "A serious complaint.",
        severity="High",
        validation_status=None,
    )
    response = client.post("/api/recovery/evaluate/F1")
    assert response.status_code == 409
    assert client.get("/api/recovery/cases").json() == []


def test_recovery_case_filters(recovery_app):
    client, sessions = recovery_app
    seed_feedback(sessions, "F1", "A serious complaint.", severity="High")
    seed_feedback(
        sessions,
        "F2",
        "Excellent support.",
        sentiment="Positive",
        severity="Low",
    )
    client.post("/api/recovery/evaluate-all")
    high = client.get("/api/recovery/cases?risk_level=High").json()
    dismissed = client.get("/api/recovery/cases?status=dismissed").json()
    assert len(high) == 1
    assert [item["feedback_id"] for item in dismissed] == ["F2"]
