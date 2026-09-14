from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.reference import load_reference_data
from backend.app.services.llm import LLMInvalidResponseError, LLMTimeoutError


class FakeLLM:
    model = "fake-structured-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def structured_response(self, *, instructions, input_text, response_model):
        self.calls += 1
        result = self.outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        try:
            return response_model.model_validate(deepcopy(result))
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


def output(
    feedback_id="F1",
    *,
    summary="The delivery was late.",
    sentiment="Negative",
    severity="Medium",
    primary_category="Delivery",
    is_mixed=False,
    confidence=0.92,
    requires_review=False,
    aspects=None,
):
    return {
        "feedback_id": feedback_id,
        "summary": summary,
        "sentiment": sentiment,
        "severity": severity,
        "primary_category": primary_category,
        "is_mixed": is_mixed,
        "confidence": confidence,
        "requires_review": requires_review,
        "aspects": aspects
        or [
            {
                "category": primary_category,
                "sentiment": sentiment,
                "severity": severity,
                "evidence_text": "delivery was late",
            }
        ],
    }


def make_client(tmp_path, references, outputs):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'classification.db'}",
        classification_review_threshold=0.70,
    )
    fake = FakeLLM(outputs)
    app = create_app(settings, llm_service=fake, reference_data=references)
    return TestClient(app), fake


def create_feedback(client, text, feedback_id="F1"):
    response = client.post(
        "/api/feedback", json={"feedback_id": feedback_id, "feedback_text": text}
    )
    assert response.status_code == 201
    return response.json()


def test_negative_delivery_feedback_saved(tmp_path, references):
    client, fake = make_client(tmp_path, references, [output()])
    with client:
        feedback = create_feedback(client, "My delivery was late by two days.")
        response = client.post(f"/api/feedback/{feedback['id']}/classify")
        assert response.status_code == 200
        analysis = response.json()
        assert analysis["feedback_id"] == "F1"
        assert analysis["sentiment"] == "Negative"
        assert analysis["severity"] == "Medium"
        assert analysis["aspects"][0]["category"] == "Delivery"
        assert analysis["model_used"] == fake.model
        assert client.get(f"/api/feedback/{feedback['id']}/analysis").json() == analysis
        raw = client.get(f"/api/feedback/{feedback['id']}").json()
        assert raw["processing_status"] == "classified"


def test_positive_feedback(tmp_path, references):
    positive = output(
        summary="Customer service was helpful.",
        sentiment="Positive",
        severity="Low",
        primary_category="Customer Service",
        aspects=[
            {
                "category": "Customer Service",
                "sentiment": "Positive",
                "severity": "Low",
                "evidence_text": "Customer service was helpful",
            }
        ],
    )
    client, _ = make_client(tmp_path, references, [positive])
    with client:
        feedback = create_feedback(client, "Customer service was helpful and polite.")
        analysis = client.post(f"/api/feedback/{feedback['id']}/classify").json()
        assert analysis["sentiment"] == "Positive"


def test_mixed_feedback_and_multiple_categories(tmp_path, references):
    mixed = output(
        summary="Delivery was quick, but support was unhelpful.",
        is_mixed=False,
        aspects=[
            {
                "category": "Delivery",
                "sentiment": "Positive",
                "severity": "Low",
                "evidence_text": "Delivery was quick",
            },
            {
                "category": "Customer Service",
                "sentiment": "Negative",
                "severity": "Medium",
                "evidence_text": "support was unhelpful",
            },
        ],
    )
    client, _ = make_client(tmp_path, references, [mixed])
    with client:
        feedback = create_feedback(client, "Delivery was quick, but support was unhelpful.")
        analysis = client.post(f"/api/feedback/{feedback['id']}/classify").json()
        assert analysis["is_mixed"] is True
        assert {aspect["category"] for aspect in analysis["aspects"]} == {
            "Delivery",
            "Customer Service",
        }


def test_ambiguous_feedback_requires_review(tmp_path, references):
    ambiguous = output(
        summary="The comment is unclear.",
        sentiment="Neutral",
        severity="Low",
        confidence=0.45,
        requires_review=False,
        aspects=[
            {
                "category": "Delivery",
                "sentiment": "Neutral",
                "severity": "Low",
                "evidence_text": "Not sure about it",
            }
        ],
    )
    client, _ = make_client(tmp_path, references, [ambiguous])
    with client:
        feedback = create_feedback(client, "Not sure about it.")
        analysis = client.post(f"/api/feedback/{feedback['id']}/classify").json()
        assert analysis["requires_review"] is True
        assert analysis["confidence"] == 0.45


@pytest.mark.parametrize(
    "bad_output",
    [
        output(sentiment="Upset"),
        output(primary_category="Fulfilment"),
        output(feedback_id="CHANGED"),
        output(
            aspects=[
                {
                    "category": "Delivery",
                    "sentiment": "Negative",
                    "severity": "Medium",
                    "evidence_text": "words that were never supplied",
                }
            ]
        ),
    ],
)
def test_invalid_llm_response_is_not_saved(tmp_path, references, bad_output):
    client, _ = make_client(tmp_path, references, [bad_output])
    with client:
        feedback = create_feedback(client, "My delivery was late by two days.")
        response = client.post(f"/api/feedback/{feedback['id']}/classify")
        assert response.status_code == 502
        assert client.get(f"/api/feedback/{feedback['id']}/analysis").status_code == 404
        raw = client.get(f"/api/feedback/{feedback['id']}").json()
        assert raw["processing_status"] == "classification_failed"


def test_completed_classification_not_reprocessed_without_force(tmp_path, references):
    client, fake = make_client(tmp_path, references, [output(), output(summary="Updated summary.")])
    with client:
        feedback = create_feedback(client, "My delivery was late by two days.")
        url = f"/api/feedback/{feedback['id']}/classify"
        original = client.post(url).json()
        assert client.post(url).json() == original
        assert fake.calls == 1
        assert client.post(f"{url}?force=true").json()["summary"] == "Updated summary."
        assert fake.calls == 2


def test_filtering_and_batch_classification(tmp_path, references):
    results = [
        output(feedback_id="F1"),
        output(
            feedback_id="F2",
            summary="Customer service was helpful.",
            sentiment="Positive",
            severity="Low",
            primary_category="Customer Service",
            requires_review=True,
            aspects=[
                {
                    "category": "Customer Service",
                    "sentiment": "Positive",
                    "severity": "Low",
                    "evidence_text": "service was helpful",
                }
            ],
        ),
    ]
    client, _ = make_client(tmp_path, references, results)
    with client:
        create_feedback(client, "My delivery was late by two days.", "F1")
        create_feedback(client, "The service was helpful.", "F2")
        summary = client.post("/api/feedback/classify-all").json()
        assert summary == {
            "total": 2,
            "processed": 2,
            "failed": 0,
            "requires_review": 1,
            "errors": [],
        }
        assert client.post("/api/feedback/classify-all").json()["total"] == 0
        positives = client.get("/api/feedback/analyses?sentiment=Positive").json()
        assert [item["feedback_id"] for item in positives] == ["F2"]
        reviewed = client.get("/api/feedback/analyses?requires_review=true").json()
        assert [item["feedback_id"] for item in reviewed] == ["F2"]
        delivery = client.get("/api/feedback/analyses?category=Delivery").json()
        assert [item["feedback_id"] for item in delivery] == ["F1"]
        assert client.get("/api/feedback/analyses?severity=Unknown").status_code == 422


def test_batch_continues_after_timeout(tmp_path, references):
    client, _ = make_client(
        tmp_path,
        references,
        [LLMTimeoutError("The OpenAI request timed out."), output(feedback_id="F2")],
    )
    with client:
        first = create_feedback(client, "My delivery was late.", "F1")
        create_feedback(client, "My delivery was late too.", "F2")
        summary = client.post("/api/feedback/classify-all").json()
        assert (summary["total"], summary["processed"], summary["failed"]) == (2, 1, 1)
        assert summary["errors"][0]["feedback_db_id"] == first["id"]


def test_missing_production_configuration_returns_503(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'missing.db'}",
        categories_path=tmp_path / "missing-categories.json",
        business_rules_path=tmp_path / "missing-rules.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/feedback/999/classify").status_code == 404
        assert client.post("/api/feedback/classify-all").json()["total"] == 0
        feedback = create_feedback(client, "Some feedback")
        response = client.post(f"/api/feedback/{feedback['id']}/classify")
        assert response.status_code == 503
        assert "reference file is missing" in response.json()["detail"]
