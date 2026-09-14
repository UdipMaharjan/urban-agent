import json
import re
from typing import Protocol

from ..models import Feedback
from ..reference import ReferenceData
from ..schemas import ClassificationResult, Sentiment, Severity
from ..services.llm import LLMInvalidResponseError


class StructuredLLM(Protocol):
    model: str

    def structured_response(self, *, instructions: str, input_text: str, response_model: type): ...


class ClassificationAgent:
    def __init__(self, llm: StructuredLLM, references: ReferenceData, review_threshold: float):
        self.llm = llm
        self.references = references
        self.review_threshold = review_threshold

    def classify(self, feedback: Feedback) -> ClassificationResult:
        categories = [category.model_dump() for category in self.references.categories.categories]
        business_context = self.references.business_rules.model_dump()
        instructions = (
            "You are UrbanAgent's Classification Agent. Classify only the supplied feedback. "
            "Return the requested structured object and no prose. Use exactly one of the allowed "
            "category names. Use Positive, Neutral, or Negative sentiment and Low, Medium, or High "
            "severity. Every aspect needs a short verbatim phrase copied from the feedback as "
            "evidence_text. Do not infer customer identity, events, causes, policies, or outcomes. "
            "Keep the summary factual and concise. Set is_mixed when praise and criticism coexist. "
            "Set requires_review for unclear meaning, uncertain category, conflicting signals, or "
            "insufficient evidence. Business rules are context, not proof that an event occurred.\n"
            f"Allowed categories: {json.dumps(categories, ensure_ascii=False)}\n"
            f"Business context and rules: {json.dumps(business_context, ensure_ascii=False)}"
        )
        result = self.llm.structured_response(
            instructions=instructions,
            input_text=json.dumps(
                {"feedback_id": feedback.feedback_id, "feedback_text": feedback.feedback_text},
                ensure_ascii=False,
            ),
            response_model=ClassificationResult,
        )
        self._validate_grounding(feedback, result)
        if result.confidence < self.review_threshold:
            result.requires_review = True
        return result

    def _validate_grounding(self, feedback: Feedback, result: ClassificationResult) -> None:
        if result.feedback_id != feedback.feedback_id:
            raise LLMInvalidResponseError("The response changed the feedback_id.")
        allowed = self.references.category_names
        categories = {aspect.category for aspect in result.aspects}
        invalid = (categories | {result.primary_category}) - allowed
        if invalid:
            raise LLMInvalidResponseError(
                f"The response used unsupported categories: {', '.join(sorted(invalid))}."
            )
        if result.primary_category not in categories:
            raise LLMInvalidResponseError("primary_category must also appear in aspects.")
        source = self._normalize(feedback.feedback_text)
        for aspect in result.aspects:
            if self._normalize(aspect.evidence_text) not in source:
                raise LLMInvalidResponseError(
                    "Each evidence_text value must be a verbatim phrase from the feedback."
                )
        sentiments = {aspect.sentiment for aspect in result.aspects}
        if Sentiment.POSITIVE in sentiments and Sentiment.NEGATIVE in sentiments:
            result.is_mixed = True
        elif len(sentiments) == 1 and result.sentiment not in sentiments:
            raise LLMInvalidResponseError(
                "Overall sentiment must match the aspect sentiment when feedback is not mixed."
            )
        severity_rank = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
        highest_aspect_severity = max(
            (aspect.severity for aspect in result.aspects), key=severity_rank.__getitem__
        )
        if result.severity != highest_aspect_severity:
            raise LLMInvalidResponseError(
                "Overall severity must match the highest aspect severity."
            )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()
