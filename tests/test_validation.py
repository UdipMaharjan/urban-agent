from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.database import create_session_factory
from backend.app.main import create_app
from backend.app.models import FeedbackAspect
from backend.app.reference import load_reference_data
from backend.app.services.llm import LLMInvalidResponseError


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


def classification_output(
    feedback_id="F1",
    *,
    sentiment="Negative",
    severity="Medium",
    category="Delivery",
    evidence="delivery was late",
    is_mixed=False,
    aspects=None,
):
    return {
        "feedback_id": feedback_id,
        "summary": "Classification summary.",
        "sentiment": sentiment,
        "severity": severity,
        "primary_category": category,
        "is_mixed": is_mixed,
        "confidence": 0.91,
        "requires_review": False,
        "aspects": aspects
        or [
            {
                "category": category,
                "sentiment": sentiment,
                "severity": severity,
                "evidence_text": evidence,
            }
        ],
    }


def validation_output(
    feedback_id="F1",
    *,
    status="approved",
    confidence=0.94,
    requires_human_review=False,
    sentiment="Negative",
    severity="Medium",
    categories=None,
    issues=None,
    summary="Classification is supported by the source feedback.",
):
    return {
        "feedback_id": feedback_id,
        "validation_status": status,
        "overall_confidence": confidence,
        "requires_human_review": requires_human_review,
        "issues": issues or [],
        "validated_sentiment": sentiment,
        "validated_severity": severity,
        "validated_categories": categories or ["Delivery"],
        "validation_summary": summary,
    }


def validation_issue(field, issue_type, message):
    return {"field": field, "issue_type": issue_type, "message": message}


def make_client(tmp_path, references, outputs, database_name="validation.db"):
    database_url = f"sqlite:///{tmp_path / database_name}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        classification_review_threshold=0.70,
        validation_review_threshold=0.70,
    )
    fake = FakeLLM(outputs)
    return (
        TestClient(create_app(settings, llm_service=fake, reference_data=references)),
        fake,
        settings,
    )


def create_feedback(client, text, feedback_id="F1"):
    response = client.post(
        "/api/feedback", json={"feedback_id": feedback_id, "feedback_text": text}
    )
    assert response.status_code == 201
    return response.json()


def create_classified(client, text, feedback_id="F1"):
    feedback = create_feedback(client, text, feedback_id)
    response = client.post(f"/api/feedback/{feedback['id']}/classify")
    assert response.status_code == 200
    return feedback, response.json()


def test_valid_negative_delivery_classification_is_approved(tmp_path, references):
    client, _, _ = make_client(tmp_path, references, [classification_output(), validation_output()])
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        response = client.post(f"/api/feedback/{feedback['id']}/validate")
        assert response.status_code == 200
        validation = response.json()
        assert validation["validation_status"] == "approved"
        assert validation["validated_categories"] == ["Delivery"]
        assert validation["requires_human_review"] is False


def test_valid_positive_staff_behaviour_is_approved(tmp_path, references):
    classifier = classification_output(
        sentiment="Positive",
        severity="Low",
        category="Staff Behaviour",
        evidence="staff member was helpful",
    )
    validator = validation_output(
        sentiment="Positive", severity="Low", categories=["Staff Behaviour"]
    )
    client, _, _ = make_client(tmp_path, references, [classifier, validator])
    with client:
        feedback, _ = create_classified(client, "The staff member was helpful and polite.")
        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        assert validation["validation_status"] == "approved"
        assert validation["validated_sentiment"] == "Positive"


def test_mixed_feedback_is_approved(tmp_path, references):
    classifier = classification_output(
        category="Product Quality",
        is_mixed=True,
        aspects=[
            {
                "category": "Product Quality",
                "sentiment": "Positive",
                "severity": "Low",
                "evidence_text": "products are good",
            },
            {
                "category": "Pricing",
                "sentiment": "Negative",
                "severity": "Medium",
                "evidence_text": "prices could be more competitive",
            },
        ],
    )
    validator = validation_output(sentiment="Mixed", categories=["Product Quality", "Pricing"])
    client, _, _ = make_client(tmp_path, references, [classifier, validator])
    with client:
        feedback, _ = create_classified(
            client,
            "The products are good but I think some prices could be more competitive.",
        )
        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        assert validation["validation_status"] == "approved"
        assert validation["validated_sentiment"] == "Mixed"


def test_wrong_category_is_approved_with_changes_and_flagged(tmp_path, references):
    classifier = classification_output(category="Product Availability")
    validator = validation_output(
        status="approved_with_changes",
        categories=["Delivery"],
        issues=[
            validation_issue(
                "category", "unsupported", "Product Availability is unrelated to the text."
            )
        ],
    )
    client, _, _ = make_client(tmp_path, references, [classifier, validator])
    with client:
        feedback, analysis = create_classified(client, "My delivery was late by two days.")
        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        assert analysis["primary_category"] == "Product Availability"
        assert validation["validated_categories"] == ["Delivery"]
        assert validation["requires_human_review"] is True


def test_wrong_sentiment_is_corrected_and_original_is_preserved(tmp_path, references):
    classifier = classification_output(
        sentiment="Negative", severity="Low", evidence="Everything was okay"
    )
    validator = validation_output(
        status="approved_with_changes",
        sentiment="Neutral",
        severity="Low",
        issues=[
            validation_issue("sentiment", "unsupported", "Negative sentiment is not supported.")
        ],
    )
    client, _, _ = make_client(tmp_path, references, [classifier, validator])
    with client:
        feedback, _ = create_classified(
            client, "Everything was okay. Nothing particularly good or bad."
        )
        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        analysis = client.get(f"/api/feedback/{feedback['id']}/analysis").json()
        assert analysis["sentiment"] == "Negative"
        assert validation["validated_sentiment"] == "Neutral"
        assert validation["requires_human_review"] is True


def test_exaggerated_severity_is_corrected(tmp_path, references):
    classifier = classification_output(severity="High")
    validator = validation_output(
        status="approved_with_changes",
        severity="Medium",
        issues=[validation_issue("severity", "unreasonable", "High severity is exaggerated.")],
    )
    client, _, _ = make_client(tmp_path, references, [classifier, validator])
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        assert validation["validated_severity"] == "Medium"
        assert validation["requires_human_review"] is True


def test_fabricated_classifier_evidence_is_rejected(tmp_path, references):
    client, _, settings = make_client(
        tmp_path, references, [classification_output(), validation_output()]
    )
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        engine, session_factory = create_session_factory(settings.database_url)
        with session_factory() as session:
            aspect = session.scalar(select(FeedbackAspect))
            aspect.evidence_text = "This phrase was fabricated"
            session.commit()
        engine.dispose()

        validation = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        assert validation["validation_status"] == "rejected"
        assert validation["requires_human_review"] is True
        assert validation["issues"][0]["issue_type"] == "fabricated"


def test_validation_requires_existing_classification(tmp_path, references):
    client, fake, _ = make_client(tmp_path, references, [])
    with client:
        feedback = create_feedback(client, "My delivery was late by two days.")
        response = client.post(f"/api/feedback/{feedback['id']}/validate")
        assert response.status_code == 409
        assert "completed classification" in response.json()["detail"]
        assert fake.calls == 0


def test_validation_is_persisted_and_retrievable(tmp_path, references):
    validator = validation_output(
        status="needs_review",
        confidence=0.55,
        requires_human_review=False,
        issues=[validation_issue("evidence_text", "ambiguous", "Evidence is ambiguous.")],
    )
    client, _, _ = make_client(tmp_path, references, [classification_output(), validator])
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        saved = client.post(f"/api/feedback/{feedback['id']}/validate").json()
        retrieved = client.get(f"/api/feedback/{feedback['id']}/validation").json()
        assert retrieved == saved
        assert retrieved["issues"][0]["field"] == "evidence_text"
        assert retrieved["requires_human_review"] is True


def test_completed_validation_is_not_repeated_without_force(tmp_path, references):
    client, fake, _ = make_client(
        tmp_path,
        references,
        [classification_output(), validation_output(), validation_output(confidence=0.88)],
    )
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        url = f"/api/feedback/{feedback['id']}/validate"
        first = client.post(url).json()
        assert client.post(url).json() == first
        assert fake.calls == 2


def test_force_true_revalidates_current_analysis(tmp_path, references):
    client, fake, _ = make_client(
        tmp_path,
        references,
        [classification_output(), validation_output(), validation_output(confidence=0.88)],
    )
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        url = f"/api/feedback/{feedback['id']}/validate"
        client.post(url)
        updated = client.post(f"{url}?force=true").json()
        assert updated["overall_confidence"] == 0.88
        assert fake.calls == 3


def test_batch_validation_summary_and_duplicate_prevention(tmp_path, references):
    classifications = [classification_output(feedback_id=f"F{i}") for i in range(1, 5)]
    validations = [
        validation_output(feedback_id="F1"),
        validation_output(
            feedback_id="F2",
            status="approved_with_changes",
            categories=["Pricing"],
            issues=[validation_issue("category", "unsupported", "Category corrected.")],
        ),
        validation_output(
            feedback_id="F3",
            status="needs_review",
            issues=[validation_issue("category", "ambiguous", "Category is ambiguous.")],
        ),
        validation_output(
            feedback_id="F4",
            status="rejected",
            issues=[validation_issue("summary", "fabricated", "Summary is unsupported.")],
        ),
    ]
    client, fake, _ = make_client(tmp_path, references, classifications + validations + validations)
    with client:
        for number in range(1, 5):
            create_feedback(client, f"My delivery was late for order {number}.", f"F{number}")
        assert client.post("/api/feedback/classify-all").json()["processed"] == 4
        summary = client.post("/api/feedback/validate-all").json()
        assert summary == {
            "total": 4,
            "validated": 2,
            "needs_review": 1,
            "rejected": 1,
            "failed": 0,
            "errors": [],
        }
        assert client.post("/api/feedback/validate-all").json()["total"] == 0
        forced = client.post("/api/feedback/validate-all?force=true").json()
        assert forced["total"] == 4
        assert (forced["validated"], forced["needs_review"], forced["rejected"]) == (
            2,
            1,
            1,
        )
        assert fake.calls == 12


def test_forced_reclassification_invalidates_stale_validation(tmp_path, references):
    client, _, _ = make_client(
        tmp_path,
        references,
        [classification_output(), validation_output(), classification_output()],
    )
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        client.post(f"/api/feedback/{feedback['id']}/validate")
        assert client.get(f"/api/feedback/{feedback['id']}/validation").status_code == 200
        response = client.post(f"/api/feedback/{feedback['id']}/classify?force=true")
        assert response.status_code == 200
        assert client.get(f"/api/feedback/{feedback['id']}/validation").status_code == 404


def test_filtering_validations(tmp_path, references):
    classifier_one = classification_output(feedback_id="F1")
    classifier_two = classification_output(feedback_id="F2")
    approved = validation_output(feedback_id="F1")
    review = validation_output(
        feedback_id="F2",
        status="needs_review",
        confidence=0.45,
        issues=[validation_issue("category", "ambiguous", "Category is uncertain.")],
    )
    client, _, _ = make_client(
        tmp_path, references, [classifier_one, classifier_two, approved, review]
    )
    with client:
        create_feedback(client, "My delivery was late for order one.", "F1")
        create_feedback(client, "My delivery was late for order two.", "F2")
        client.post("/api/feedback/classify-all")
        client.post("/api/feedback/validate-all")
        reviewed = client.get(
            "/api/feedback/validations?validation_status=needs_review&requires_human_review=true"
        ).json()
        assert [item["feedback_id"] for item in reviewed] == ["F2"]
        approved_results = client.get("/api/feedback/validations?validation_status=approved").json()
        assert [item["feedback_id"] for item in approved_results] == ["F1"]
        assert client.get("/api/feedback/validations?validation_status=unknown").status_code == 422


def test_invalid_validator_output_is_not_saved(tmp_path, references):
    invalid = validation_output()
    invalid["validation_status"] = "accepted"
    client, _, _ = make_client(tmp_path, references, [classification_output(), invalid])
    with client:
        feedback, _ = create_classified(client, "My delivery was late by two days.")
        response = client.post(f"/api/feedback/{feedback['id']}/validate")
        assert response.status_code == 502
        assert client.get(f"/api/feedback/{feedback['id']}/validation").status_code == 404
        raw = client.get(f"/api/feedback/{feedback['id']}").json()
        assert raw["processing_status"] == "validation_failed"
