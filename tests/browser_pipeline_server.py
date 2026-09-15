"""Offline browser fixture only. Never imported by the production application."""

import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.responses import Response
from openpyxl import Workbook
from test_validation import classification_output, validation_output

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.reference import load_reference_data
from backend.app.schemas import ClassificationResult

temporary = TemporaryDirectory(prefix="urbanagent-browser-")
root = Path(__file__).resolve().parents[1]


class BrowserLLM:
    model = "offline-browser-fixture"
    calls = 0

    def structured_response(self, *, instructions, input_text, response_model):
        self.calls += 1
        payload = json.loads(input_text)
        if response_model is ClassificationResult:
            result = classification_output(payload["feedback_id"])
        else:
            feedback_id = payload["original_feedback"]["feedback_id"]
            result = validation_output(feedback_id)
            if feedback_id.endswith("REVIEW"):
                result = validation_output(
                    feedback_id,
                    status="needs_review",
                    requires_human_review=True,
                    issues=[
                        {
                            "field": "severity",
                            "issue_type": "ambiguous",
                            "message": "Review the reported impact.",
                        }
                    ],
                )
        return response_model.model_validate(result)


fake = BrowserLLM()
app = create_app(
    Settings(
        _env_file=None,
        database_url=f"sqlite:///{Path(temporary.name) / 'browser.db'}",
        openai_api_key="",
        openai_model="",
    ),
    llm_service=fake,
    reference_data=load_reference_data(
        root / "data/reference/categories.json", root / "data/reference/business_rules.json"
    ),
)


@app.get("/__test__/identity")
def identity():
    return {"offline_fixture": True, "llm_calls": fake.calls}


@app.get("/__test__/workbook")
def workbook(single: bool = False):
    book = Workbook()
    sheet = book.active
    sheet.append(["feedback_id", "feedback_text", "submitted_at"])
    ids = ["UI-SINGLE"] if single else ["UI-A", "UI-REVIEW"]
    for feedback_id in ids:
        sheet.append([feedback_id, "My delivery was late by two days.", "2026-09-01"])
    output = BytesIO()
    book.save(output)
    book.close()
    return Response(
        output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
