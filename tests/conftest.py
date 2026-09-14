from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def make_excel():
    def build(rows, headers=None, extra_sheet=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers if headers is not None else ["feedback_id", "feedback_text"])
        for row in rows:
            sheet.append(row)
        if extra_sheet:
            workbook.create_sheet("Other")
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    return build


@pytest.fixture
def upload(client):
    def send(content, filename="feedback.xlsx"):
        return client.post(
            "/api/import/excel",
            files={
                "file": (
                    filename,
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    return send
