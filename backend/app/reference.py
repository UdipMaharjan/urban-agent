import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class CategoryDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)


class CategoryCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryDefinition] = Field(min_length=1)


class BusinessRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    rule: str = Field(min_length=1, max_length=1000)


class ClassificationGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentiment: dict[str, str]
    severity: dict[str, str]

    @model_validator(mode="after")
    def require_exact_labels(self):
        if set(self.sentiment) != {"Positive", "Neutral", "Negative"}:
            raise ValueError("Sentiment guidance must define Positive, Neutral, and Negative.")
        if set(self.severity) != {"Low", "Medium", "High"}:
            raise ValueError("Severity guidance must define Low, Medium, and High.")
        if any(
            not definition.strip()
            for definition in (*self.sentiment.values(), *self.severity.values())
        ):
            raise ValueError("Classification guidance definitions must not be blank.")
        return self


class BusinessRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business: str = Field(min_length=1, max_length=1000)
    main_customer_channels: list[str] = Field(min_length=1)
    rules: list[BusinessRule]
    management_priority: str = Field(min_length=1, max_length=1000)
    improvement_approach: str = Field(min_length=1, max_length=1000)
    decision_authority: str = Field(min_length=1, max_length=1000)
    classification_guidance: ClassificationGuidance


class ReferenceData(BaseModel):
    categories: CategoryCatalog
    business_rules: BusinessRules

    @property
    def category_names(self) -> set[str]:
        return {category.name for category in self.categories.categories}


class ReferenceDataError(RuntimeError):
    pass


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReferenceDataError(f"Required reference file is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceDataError(f"Reference file is not valid JSON: {path}") from exc


def load_reference_data(categories_path: Path, business_rules_path: Path) -> ReferenceData:
    try:
        references = ReferenceData(
            categories=CategoryCatalog.model_validate(_read_json(categories_path)),
            business_rules=BusinessRules.model_validate(_read_json(business_rules_path)),
        )
    except ValidationError as exc:
        raise ReferenceDataError(f"Reference data has an invalid structure: {exc}") from exc

    names = [category.name for category in references.categories.categories]
    if len(names) != len(set(names)):
        raise ReferenceDataError("Category names must be unique.")
    unknown_rule_categories = {
        rule.category for rule in references.business_rules.rules
    } - references.category_names
    if unknown_rule_categories:
        unknown = ", ".join(sorted(unknown_rule_categories))
        raise ReferenceDataError(f"Business rules use unknown categories: {unknown}.")
    return references
