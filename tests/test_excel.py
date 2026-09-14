from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_valid_excel_import(client, make_excel, upload):
    content = make_excel([["001", "Helpful staff"], ["002", "Please extend opening hours"]])
    response = upload(content)
    assert response.status_code == 200
    assert response.json() == {
        "total_rows": 2,
        "imported_rows": 2,
        "skipped_rows": 0,
        "failed_rows": 0,
        "errors": [],
    }
    records = client.get("/api/feedback").json()
    assert [record["feedback_id"] for record in records] == ["001", "002"]
    repeated = upload(content).json()
    assert repeated["imported_rows"] == 0
    assert repeated["skipped_rows"] == 2
    assert [error["row"] for error in repeated["errors"]] == [2, 3]
    assert len(client.get("/api/feedback").json()) == 2


def test_full_columns_and_excel_dates(client, make_excel, upload):
    content = make_excel(
        [
            [
                "F1",
                "university_dataset",
                datetime(2026, 9, 1, 10),
                4,
                "Sample",
                "a@example.com",
                "Text",
            ],
            ["F2", None, None, None, None, None, "Other text"],
        ],
        headers=[
            "feedback_id",
            "source",
            "submitted_at",
            "rating",
            "customer_name",
            "customer_email",
            "feedback_text",
        ],
    )
    assert upload(content).json()["imported_rows"] == 2
    records = client.get("/api/feedback").json()
    assert records[0]["submitted_at"] == "2026-09-01T10:00:00Z"
    assert records[0]["rating"] == 4
    assert records[0]["source"] == "university_dataset"
    assert records[1]["source"] == "manual"
    assert records[1]["submitted_at"] is None


def test_every_row_accounted_for(client, make_excel, upload):
    content = make_excel(
        [
            ["F1", "Original"],
            ["F1", "Original"],
            ["F1", "Changed"],
            ["F2", None],
            [None, "Missing ID"],
            [None, None],
            ["F3", "Valid"],
        ]
    )
    summary = upload(content).json()
    assert (
        summary["total_rows"],
        summary["imported_rows"],
        summary["skipped_rows"],
        summary["failed_rows"],
    ) == (7, 2, 2, 3)
    assert [issue["row"] for issue in summary["errors"]] == [3, 4, 5, 6, 7]
    assert [issue["code"] for issue in summary["errors"]] == [
        "duplicate",
        "conflict",
        "validation_error",
        "validation_error",
        "blank_row",
    ]
    assert [r["feedback_text"] for r in client.get("/api/feedback").json()] == ["Original", "Valid"]


@pytest.mark.parametrize(
    "headers, rows, extra_sheet, expected",
    [
        (["feedback_id"], [["F1"]], False, "Missing required columns"),
        (["feedback_text"], [["Text"]], False, "Missing required columns"),
        (
            ["feedback_id", "feedback_text", "feedback_id"],
            [["F1", "Text", "F2"]],
            False,
            "Duplicate",
        ),
        (["feedback_id", "feedback_text", "extra"], [["F1", "Text", "x"]], False, "Unknown"),
        (["feedback_id", "feedback_text"], [["F1", "Text"]], True, "exactly one worksheet"),
        (["feedback_id", "feedback_text"], [], False, "no data rows"),
        (
            ["feedback_id", "feedback_text"],
            [["F1", "Text"], ["F2", "Text", "lost"]],
            False,
            "without a column header",
        ),
    ],
)
def test_invalid_structure_is_atomic(
    client, make_excel, upload, headers, rows, extra_sheet, expected
):
    response = upload(make_excel(rows, headers=headers, extra_sheet=extra_sheet))
    assert response.status_code == 400
    assert expected in response.json()["detail"]
    assert client.get("/api/feedback").json() == []


@pytest.mark.parametrize(
    "content, filename",
    [(b"garbage", "bad.xlsx"), (b"", "empty.xlsx"), (b"a,b", "file.csv"), (b"123", "file.xls")],
)
def test_malformed_upload(client, upload, content, filename):
    response = upload(content, filename)
    assert response.status_code == 400
    assert response.json()["detail"]
    assert client.get("/api/feedback").json() == []


def test_formula_error_numeric_id_and_invalid_values(make_excel, upload):
    content = make_excel(
        [
            ["F1", "=1+1", None, None],
            ["F2", "#DIV/0!", None, None],
            [123, "Numeric ID", None, None],
            ["F4", "Text", "bad", None],
            ["F5", "Text", None, "yesterday"],
            ["F6", "Text", "nan", None],
        ],
        headers=["feedback_id", "feedback_text", "rating", "submitted_at"],
    )
    summary = upload(content).json()
    assert summary["failed_rows"] == summary["total_rows"] == 6
    assert summary["imported_rows"] == 0
    assert all(issue["code"] == "validation_error" for issue in summary["errors"])


def test_api_and_excel_share_duplicate_boundary(client, make_excel, upload):
    payload = {"feedback_id": "F1", "feedback_text": "Same raw record"}
    assert client.post("/api/feedback", json=payload).status_code == 201
    assert upload(make_excel([["F1", "Same raw record"]])).json()["skipped_rows"] == 1


@pytest.mark.parametrize(
    "setting, value, status",
    [
        ("max_upload_bytes", 10, 413),
        ("max_import_rows", 1, 400),
        ("max_excel_uncompressed_bytes", 10, 400),
    ],
)
def test_import_limits(tmp_path, make_excel, setting, value, status):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'limits.db'}", **{setting: value}
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/import/excel",
            files={"file": ("large.xlsx", make_excel([["F1", "Text"], ["F2", "Text"]]))},
        )
        assert response.status_code == status
        assert client.get("/api/feedback").json() == []


def test_sample_template_import(upload):
    path = Path(__file__).resolve().parents[1] / "data/sample/feedback_template.xlsx"
    summary = upload(path.read_bytes()).json()
    assert summary["total_rows"] == summary["imported_rows"] == 3
    assert summary["errors"] == []
