import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_feedback(client):
    response = client.post(
        "/api/feedback",
        json={"feedback_id": "001", "feedback_text": " Staff answered my question. "},
    )
    assert response.status_code == 201
    record = response.json()
    assert record["feedback_id"] == "001"
    assert record["source"] == "manual"
    assert record["processing_status"] == "pending"
    assert record["submitted_at"] is None
    assert record["rating"] is None
    assert record["customer_email"] is None
    assert record["created_at"].endswith("Z")
    assert record["feedback_text"] == " Staff answered my question. "
    assert client.get(f"/api/feedback/{record['id']}").json() == record
    assert client.get("/api/feedback/99999").status_code == 404


def test_listing_and_pagination(client):
    assert client.get("/api/feedback").json() == []
    for i in range(3):
        assert (
            client.post(
                "/api/feedback", json={"feedback_id": str(i), "feedback_text": "Example feedback"}
            ).status_code
            == 201
        )
    records = client.get("/api/feedback").json()
    assert [record["feedback_id"] for record in records] == ["0", "1", "2"]
    assert client.get("/api/feedback?offset=1&limit=1").json() == records[1:2]
    assert client.get("/api/feedback?offset=-1").status_code == 422
    assert client.get("/api/feedback?limit=101").status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"feedback_id": " "},
        {"feedback_text": "\n\t"},
        {"rating": "bad"},
        {"submitted_at": "yesterday"},
        {"submitted_at": 12345},
        {"rating": True},
        {"processing_status": "validated"},
        {"feedback_id": 123},
        {"source": ""},
    ],
)
def test_invalid_payload(client, change):
    payload = {"feedback_id": "F1", "feedback_text": "Sample"} | change
    assert client.post("/api/feedback", json=payload).status_code == 422
    assert client.get("/api/feedback").json() == []


def test_duplicate_conflict_and_source_namespace(client):
    payload = {"feedback_id": " F1 ", "source": " forms ", "feedback_text": "Sample"}
    assert client.post("/api/feedback", json=payload).status_code == 201
    duplicate = client.post("/api/feedback", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate"
    conflict = client.post("/api/feedback", json=payload | {"feedback_text": "Changed"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "conflict"
    assert client.post("/api/feedback", json=payload | {"source": "gmail"}).status_code == 201
    assert client.get("/api/feedback").json()[0]["feedback_text"] == "Sample"


def test_date_normalization_and_persistence(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'persistent.db'}")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/feedback",
            json={
                "feedback_id": "F1",
                "feedback_text": "Sample",
                "rating": 0,
                "submitted_at": "2026-09-14T12:00:00+05:45",
            },
        )
        assert response.status_code == 201
    with TestClient(create_app(settings)) as client:
        record = client.get("/api/feedback").json()[0]
        assert record["submitted_at"] == "2026-09-14T06:15:00Z"
        assert record["rating"] == 0
