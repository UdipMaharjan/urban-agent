import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
from backend.app.services.llm import LLMInvalidResponseError


class FakeLLM:
    model = "fake-recommendation-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def structured_response(self, *, instructions, input_text, response_model):
        self.calls.append({"instructions": instructions, "input_text": input_text})
        output = self.outputs.pop(0)
        try:
            return response_model.model_validate(deepcopy(output))
        except ValidationError as exc:
            raise LLMInvalidResponseError(
                "OpenAI returned an invalid structured response."
            ) from exc


@pytest.fixture
def references():
    root = Path(__file__).resolve().parents[1]
    return load_reference_data(
        root / "data/reference/categories.json",
        root / "data/reference/business_rules.json",
    )


def recommendation_output(category="Delivery", ids=("F1", "F2", "F3"), priority="High"):
    return {
        "category": category,
        "priority": priority,
        "problem_summary": f"Recurring negative {category} feedback is present.",
        "recommendation": "Review the current process and introduce a practical service check.",
        "business_rationale": "The action is proportionate to the validated evidence.",
        "supporting_feedback_ids": list(ids),
        "evidence_count": len(ids),
        "requires_management_approval": True,
        "confidence": 0.9,
    }


def make_app(tmp_path, references, outputs):
    database_url = f"sqlite:///{tmp_path / 'recommendations.db'}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        trend_min_feedback=3,
    )
    fake = FakeLLM(outputs)
    app = create_app(settings, llm_service=fake, reference_data=references)
    return TestClient(app), fake, database_url


def seed_validated(
    session_factory,
    feedback_id,
    *,
    category="Delivery",
    sentiment="Negative",
    severity="Medium",
):
    feedback = Feedback(
        feedback_id=feedback_id,
        source="survey",
        submitted_at=datetime(2026, 9, 8, 10),
        feedback_text=f"Validated {category} feedback for {feedback_id}.",
        processing_status="validated",
    )
    analysis = FeedbackAnalysis(
        feedback=feedback,
        primary_category=category,
        sentiment=sentiment,
        severity=severity,
        summary=f"Customer reported a {category} experience.",
        is_mixed=False,
        confidence=0.9,
        requires_review=False,
        analysis_status="completed",
        model_used="fake-classifier",
    )
    analysis.aspects.append(
        FeedbackAspect(
            category=category,
            sentiment=sentiment,
            severity=severity,
            evidence_text=f"Validated {category} feedback",
        )
    )
    validation = FeedbackValidation(
        analysis=analysis,
        validation_status="approved",
        overall_confidence=0.9,
        requires_human_review=False,
        validated_sentiment=sentiment,
        validated_severity=severity,
        validation_summary="Classification is supported by the source feedback.",
        model_used="fake-validator",
    )
    validation.categories.append(ValidationCategory(category=category))
    with session_factory() as session:
        session.add(feedback)
        session.commit()


def seed_category_trend(session_factory, category, sentiment="Negative", prefix="F"):
    for number in range(1, 4):
        seed_validated(
            session_factory,
            f"{prefix}{number}",
            category=category,
            sentiment=sentiment,
            severity="Low" if sentiment == "Positive" else "Medium",
        )


def setup_database(client, database_url):
    client.__enter__()
    engine, session_factory = create_session_factory(database_url)
    return engine, session_factory


def test_recurring_negative_trend_generates_recommendation(tmp_path, references):
    client, fake, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        result = client.post("/api/recommendations/generate").json()
        assert result["eligible_trends"] == 1
        assert result["generated"] == 1
        assert result["recommendations"][0]["approval_status"] == "pending"
        assert result["recommendations"][0]["requires_management_approval"] is True
        assert len(fake.calls) == 1
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_positive_pattern_does_not_generate_corrective_recommendation(tmp_path, references):
    client, fake, url = make_app(tmp_path, references, [])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Staff Behaviour", "Positive")
        result = client.post("/api/recommendations/generate").json()
        assert result["eligible_trends"] == 0
        assert result["generated"] == 0
        assert fake.calls == []
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_recommendation_preserves_all_evidence_ids(tmp_path, references):
    client, _, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        item = client.post("/api/recommendations/generate").json()["recommendations"][0]
        assert item["supporting_feedback_ids"] == ["F1", "F2", "F3"]
        assert item["evidence_count"] == 3
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_relevant_business_rule_is_passed_to_agent(tmp_path, references):
    client, fake, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        client.post("/api/recommendations/generate")
        agent_input = json.loads(fake.calls[0]["input_text"])
        rules = agent_input["business_context"]["relevant_rules"]
        assert rules == ["Standard orders are normally delivered within 2 to 3 working days."]
        assert "management must approve" in agent_input["business_context"]["decision_authority"]
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_invalid_structured_recommendation_is_reported(tmp_path, references):
    client, _, url = make_app(tmp_path, references, [recommendation_output(priority="Urgent")])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        result = client.post("/api/recommendations/generate").json()
        assert (result["generated"], result["failed"]) == (0, 1)
        assert client.get("/api/recommendations").json() == []
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_duplicate_recommendation_is_skipped(tmp_path, references):
    client, fake, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        assert client.post("/api/recommendations/generate").json()["generated"] == 1
        repeated = client.post("/api/recommendations/generate").json()
        assert repeated["generated"] == 0
        assert repeated["skipped_duplicates"] == 1
        assert len(fake.calls) == 1
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_recommendation_approval_endpoint_records_history(tmp_path, references):
    client, _, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        item = client.post("/api/recommendations/generate").json()["recommendations"][0]
        approved = client.patch(
            f"/api/recommendations/{item['id']}/approval",
            json={"approval_status": "approved"},
        ).json()
        assert approved["approval_status"] == "approved"
        assert approved["approval_history"][-1]["decision"] == "approved"
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_recommendation_rejection_endpoint_records_history(tmp_path, references):
    client, _, url = make_app(tmp_path, references, [recommendation_output()])
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery")
        item = client.post("/api/recommendations/generate").json()["recommendations"][0]
        rejected = client.patch(
            f"/api/recommendations/{item['id']}/approval",
            json={"approval_status": "rejected"},
        ).json()
        assert rejected["approval_status"] == "rejected"
        assert rejected["requires_management_approval"] is True
    finally:
        engine.dispose()
        client.__exit__(None, None, None)


def test_filtering_recommendations(tmp_path, references):
    outputs = [
        recommendation_output("Delivery", ("D1", "D2", "D3"), "High"),
        recommendation_output("Customer Service", ("S1", "S2", "S3"), "Medium"),
    ]
    client, _, url = make_app(tmp_path, references, outputs)
    engine, sessions = setup_database(client, url)
    try:
        seed_category_trend(sessions, "Delivery", prefix="D")
        seed_category_trend(sessions, "Customer Service", prefix="S")
        generated = client.post("/api/recommendations/generate").json()["recommendations"]
        service_item = next(item for item in generated if item["category"] == "Customer Service")
        client.patch(
            f"/api/recommendations/{service_item['id']}/approval",
            json={"approval_status": "rejected"},
        )
        high = client.get("/api/recommendations?priority=High").json()
        rejected = client.get("/api/recommendations?approval_status=rejected").json()
        delivery = client.get("/api/recommendations?category=Delivery").json()
        assert [item["category"] for item in high] == ["Delivery"]
        assert [item["category"] for item in rejected] == ["Customer Service"]
        assert [item["category"] for item in delivery] == ["Delivery"]
    finally:
        engine.dispose()
        client.__exit__(None, None, None)
