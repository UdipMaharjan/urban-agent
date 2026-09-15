from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_validation import FakeLLM, classification_output, create_feedback, validation_output

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.reference import load_reference_data
from backend.app.services.llm import LLMInvalidResponseError, LLMServiceError, LLMTimeoutError
from backend.app.services.recovery import RecoveryService


@pytest.fixture
def pipeline_app(tmp_path):
    fake = FakeLLM([])
    root = Path(__file__).resolve().parents[1]
    references = load_reference_data(
        root / "data/reference/categories.json", root / "data/reference/business_rules.json"
    )
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'pipeline.db'}")
    with TestClient(create_app(settings, llm_service=fake, reference_data=references)) as client:
        yield client, fake


def add(client, feedback_id="F1"):
    return create_feedback(client, "My delivery was late by two days.", feedback_id)["id"]


def test_new_record_runs_both_stages_and_updates_recovery(pipeline_app):
    client, fake = pipeline_app
    fake.outputs = [classification_output(), validation_output()]
    id = add(client)
    result = client.post(f"/api/feedback/{id}/analyze").json()
    assert result["status"] == "completed"
    assert result["analysis"]["feedback_id"] == result["validation"]["feedback_id"] == "F1"
    assert result["recovery"] is not None
    assert fake.calls == 2
    assert client.get("/api/feedback/analysis-state").json() == {
        "total": 1,
        "pending": 0,
        "requires_review": 0,
        "is_running": False,
    }
    assert client.get("/api/analytics/overview").json()["trusted_validated_feedback_count"] == 1


def test_existing_classification_only_needs_validation(pipeline_app):
    client, fake = pipeline_app
    fake.outputs = [classification_output(), validation_output()]
    id = add(client)
    previous = client.post(f"/api/feedback/{id}/classify").json()
    result = client.post(f"/api/feedback/{id}/analyze").json()
    assert fake.calls == 2
    assert result["analysis"] == previous


def test_complete_reuses_and_force_replaces_current_results(pipeline_app):
    client, fake = pipeline_app
    fake.outputs = [classification_output(), validation_output()] * 2
    id = add(client)
    first = client.post(f"/api/feedback/{id}/analyze").json()
    client.patch(
        f"/api/recovery/cases/{first['recovery']['id']}/status", json={"status": "resolved"}
    )
    reuse = client.post(f"/api/feedback/{id}/analyze").json()
    assert reuse["reused"] and fake.calls == 2
    assert reuse["recovery"]["status"] == "resolved"
    forced = client.post(f"/api/feedback/{id}/analyze?force=true").json()
    assert forced["status"] == "completed" and not forced["reused"]
    assert fake.calls == 4
    assert forced["recovery"]["status"] != "resolved"
    assert len(client.get("/api/feedback/validations").json()) == 1


def test_batch_isolates_failures_and_counts_review_separately(pipeline_app):
    client, fake = pipeline_app
    for id in ["F1", "F2", "F3", "F4"]:
        add(client, id)
    fake.outputs = [
        classification_output("F1"),
        validation_output("F1"),
        LLMServiceError("secret-do-not-expose"),
        classification_output("F3"),
        LLMTimeoutError("timeout"),
        classification_output("F4"),
        validation_output(
            "F4",
            status="needs_review",
            requires_human_review=True,
            issues=[
                {
                    "field": "severity",
                    "issue_type": "ambiguous",
                    "message": "The impact requires a human check.",
                }
            ],
        ),
    ]
    response = client.post("/api/feedback/analyze-pending")
    assert response.status_code == 200
    result = response.json()
    assert [
        result[k]
        for k in [
            "total_pending",
            "completed",
            "requires_review",
            "failed",
            "classification_failures",
            "validation_failures",
        ]
    ] == [4, 1, 1, 2, 1, 1]
    assert "secret-do-not-expose" not in response.text
    assert [r["feedback_id"] for r in result["results"] if r["error"]] == ["F2", "F3"]
    assert result["results"][2]["analysis"] is not None
    assert client.get("/api/feedback/analysis-state").json()["pending"] == 2
    fake.outputs = [classification_output("F2"), validation_output("F2"), validation_output("F3")]
    retry = client.post("/api/feedback/analyze-pending").json()
    assert retry["total_pending"] == retry["completed"] == 2
    assert fake.calls == 10  # F3's saved classification was reused.


def test_no_pending_makes_no_calls_even_without_key(client):
    assert client.post("/api/feedback/analyze-pending").json()["total_pending"] == 0


def test_missing_key_is_a_traceable_safe_failure(client):
    id = add(client)
    result = client.post(f"/api/feedback/{id}/analyze").json()
    assert result["status"] == "failed"
    assert result["error"]["stage"] == "classification"
    assert result["error"]["code"] == "unavailable"


def test_invalid_output_is_retained_as_failure(pipeline_app):
    client, fake = pipeline_app
    fake.outputs = [LLMInvalidResponseError("invalid")]
    id = add(client)
    result = client.post(f"/api/feedback/{id}/analyze").json()
    assert result["error"]["code"] == "invalid_response"
    assert client.get(f"/api/feedback/{id}").json()["processing_status"] == "classification_failed"


def test_failed_force_classification_keeps_previous_complete_result(pipeline_app):
    client, fake = pipeline_app
    fake.outputs = [classification_output(), validation_output(), LLMServiceError("failed")]
    id = add(client)
    first = client.post(f"/api/feedback/{id}/analyze").json()
    failure = client.post(f"/api/feedback/{id}/analyze?force=true").json()
    assert failure["status"] == "failed"
    assert failure["validation"] == first["validation"]
    assert client.get("/api/feedback/analysis-state").json()["pending"] == 0


def test_recovery_failure_can_resume_without_paid_calls(pipeline_app, monkeypatch):
    client, fake = pipeline_app
    fake.outputs = [classification_output(), validation_output()]
    id = add(client)
    original = RecoveryService.evaluate_validation

    def fail(self, validation):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(RecoveryService, "evaluate_validation", fail)
    result = client.post(f"/api/feedback/{id}/analyze").json()
    assert result["error"]["stage"] == "recovery"
    assert client.get("/api/feedback/analysis-state").json()["pending"] == 1
    monkeypatch.setattr(RecoveryService, "evaluate_validation", original)
    assert client.post("/api/feedback/analyze-pending").json()["completed"] == 1
    assert fake.calls == 2


def test_running_guard_rejects_duplicate_submissions(pipeline_app):
    client, fake = pipeline_app
    id = add(client)
    with client.app.state.analysis_lock:
        assert client.get("/api/feedback/analysis-state").json()["is_running"]
        assert client.post(f"/api/feedback/{id}/analyze?force=true").status_code == 409
        assert client.post("/api/feedback/analyze-pending").status_code == 409
    assert fake.calls == 0
    assert client.post("/api/feedback/999/analyze").status_code == 404
