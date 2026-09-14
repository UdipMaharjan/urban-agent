import json
from pathlib import Path

import pytest

from backend.app.reference import ReferenceDataError, load_reference_data

ROOT = Path(__file__).resolve().parents[1]


def valid_business_rules():
    return {
        "business": "Business description.",
        "main_customer_channels": ["Website"],
        "rules": [{"id": "delivery-target", "category": "Delivery", "rule": "Rule from brief"}],
        "management_priority": "Priority.",
        "improvement_approach": "Approach.",
        "decision_authority": "Management approves changes.",
        "classification_guidance": {
            "sentiment": {
                "Positive": "Positive definition.",
                "Neutral": "Neutral definition.",
                "Negative": "Negative definition.",
            },
            "severity": {
                "Low": "Low definition.",
                "Medium": "Medium definition.",
                "High": "High definition.",
            },
        },
    }


def write_reference_files(tmp_path, categories, business_rules=None):
    category_path = tmp_path / "categories.json"
    rules_path = tmp_path / "business_rules.json"
    category_path.write_text(json.dumps({"categories": categories}), encoding="utf-8")
    rules_path.write_text(json.dumps(business_rules or valid_business_rules()), encoding="utf-8")
    return category_path, rules_path


def test_real_urbanmart_reference_files_load():
    references = load_reference_data(
        ROOT / "data/reference/categories.json",
        ROOT / "data/reference/business_rules.json",
    )
    assert [category.name for category in references.categories.categories] == [
        "Delivery",
        "Product Quality",
        "Pricing",
        "Product Availability",
        "Customer Service",
        "Staff Behaviour",
        "Store Experience",
        "Website / App",
        "Other",
    ]
    assert "Delivery" in references.category_names
    assert "Website / App" in references.category_names
    rules = {rule.id: rule.rule for rule in references.business_rules.rules}
    assert "2 to 3 working days" in rules["delivery-promise"]
    assert "within 24 hours" in rules["customer-service-response-goal"]
    assert "management must approve" in references.business_rules.decision_authority


@pytest.mark.parametrize(
    "categories, business_rules",
    [
        ([], None),
        (
            [
                {"name": "Delivery", "description": "A"},
                {"name": "Delivery", "description": "B"},
            ],
            None,
        ),
        (
            [{"name": "Delivery", "description": "A"}],
            valid_business_rules()
            | {"rules": [{"id": "x", "category": "Unknown", "rule": "Rule"}]},
        ),
        (
            [{"name": "Delivery", "description": "A"}],
            valid_business_rules()
            | {
                "classification_guidance": {
                    "sentiment": {"Positive": "Only one."},
                    "severity": {
                        "Low": "Low.",
                        "Medium": "Medium.",
                        "High": "High.",
                    },
                }
            },
        ),
    ],
)
def test_invalid_reference_files_rejected(tmp_path, categories, business_rules):
    paths = write_reference_files(tmp_path, categories, business_rules)
    with pytest.raises(ReferenceDataError):
        load_reference_data(*paths)
