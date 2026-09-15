import json
import re

from ..models import FeedbackAnalysis
from ..reference import ReferenceData
from ..schemas import (
    ValidationIssueResult,
    ValidationIssueType,
    ValidationResult,
    ValidationStatus,
)
from ..services.llm import LLMInvalidResponseError
from .classifier import StructuredLLM


class ValidationAgent:
    """Independently checks whether a classification is supported by its source."""

    def __init__(self, llm: StructuredLLM, references: ReferenceData, review_threshold: float):
        self.llm = llm
        self.references = references
        self.review_threshold = review_threshold

    def validate(self, analysis: FeedbackAnalysis) -> ValidationResult:
        feedback = analysis.feedback
        categories = [category.model_dump() for category in self.references.categories.categories]
        business_context = self.references.business_rules.model_dump()
        classifier_result = {
            "feedback_id": feedback.feedback_id,
            "summary": analysis.summary,
            "sentiment": analysis.sentiment,
            "severity": analysis.severity,
            "primary_category": analysis.primary_category,
            "is_mixed": analysis.is_mixed,
            "confidence": analysis.confidence,
            "requires_review": analysis.requires_review,
            "aspects": [
                {
                    "category": aspect.category,
                    "sentiment": aspect.sentiment,
                    "severity": aspect.severity,
                    "evidence_text": aspect.evidence_text,
                }
                for aspect in analysis.aspects
            ],
        }
        instructions = (
            "You are UrbanAgent's independent Validation Agent. Review the original customer "
            "feedback and the separate Classification Agent result. Do not assume the classifier "
            "is correct and do not copy its confidence without assessing it. Check category "
            "relevance, sentiment, severity, mixed-feedback status, missing aspects, unsupported "
            "facts, and whether every evidence excerpt is grounded in the source. Return only the "
            "requested structured object. Use only the supplied category names. "
            "validated_sentiment must be Positive, Neutral, Negative, or Mixed. "
            "validated_severity must be Low, Medium, or High. Use approved only when the result is "
            "fully supported and issues is empty. Use "
            "approved_with_changes for supported corrections, needs_review for material ambiguity, "
            "and rejected for classifications that are substantially unsupported or fabricated. "
            "Each non-approved result must include specific structured issues. Never invent "
            "customer information, causes, policies, or outcomes. Business rules provide context "
            "only; they "
            "are not evidence that an event occurred. Do not provide chain-of-thought or hidden "
            "reasoning; give only concise findings in issue messages and validation_summary.\n"
            f"Allowed categories: {json.dumps(categories, ensure_ascii=False)}\n"
            "Business context and label guidance: "
            f"{json.dumps(business_context, ensure_ascii=False)}"
        )
        result = self.llm.structured_response(
            instructions=instructions,
            input_text=json.dumps(
                {
                    "original_feedback": {
                        "feedback_id": feedback.feedback_id,
                        "feedback_text": feedback.feedback_text,
                    },
                    "classifier_result": classifier_result,
                },
                ensure_ascii=False,
            ),
            response_model=ValidationResult,
        )
        self._validate_result(analysis, result)
        self._enforce_grounding(analysis, result)
        self._enforce_human_review(analysis, result)
        return result

    def _validate_result(self, analysis: FeedbackAnalysis, result: ValidationResult) -> None:
        if result.feedback_id != analysis.feedback.feedback_id:
            raise LLMInvalidResponseError("The validation response changed the feedback_id.")

        invalid = set(result.validated_categories) - self.references.category_names
        if invalid:
            raise LLMInvalidResponseError(
                f"The validation response used unsupported categories: "
                f"{', '.join(sorted(invalid))}."
            )
        if len(result.validated_categories) != len(set(result.validated_categories)):
            raise LLMInvalidResponseError("validated_categories must not contain duplicates.")

        material_disagreement = self._materially_disagrees(analysis, result)
        if result.validation_status == ValidationStatus.APPROVED:
            if result.issues:
                raise LLMInvalidResponseError(
                    "An approved validation result cannot contain issues."
                )
            if material_disagreement:
                raise LLMInvalidResponseError(
                    "An approved validation result cannot change classifier fields."
                )
        elif not result.issues:
            raise LLMInvalidResponseError("A non-approved validation result must contain an issue.")
        elif (
            result.validation_status == ValidationStatus.APPROVED_WITH_CHANGES
            and not material_disagreement
        ):
            raise LLMInvalidResponseError(
                "approved_with_changes must include a change to a validated field."
            )

    def _enforce_grounding(self, analysis: FeedbackAnalysis, result: ValidationResult) -> None:
        source = self._normalize(analysis.feedback.feedback_text)
        invalid_categories = {
            aspect.category for aspect in analysis.aspects
        } - self.references.category_names
        fabricated_evidence = [
            aspect
            for aspect in analysis.aspects
            if self._normalize(aspect.evidence_text) not in source
        ]
        if not invalid_categories and not fabricated_evidence:
            return

        existing = {(issue.field, issue.issue_type) for issue in result.issues}
        if (
            invalid_categories
            and (
                "category",
                ValidationIssueType.INVALID,
            )
            not in existing
        ):
            result.issues.append(
                ValidationIssueResult(
                    field="category",
                    issue_type=ValidationIssueType.INVALID,
                    message="The classifier used a category outside the approved UrbanMart list.",
                )
            )
        if (
            fabricated_evidence
            and (
                "evidence_text",
                ValidationIssueType.FABRICATED,
            )
            not in existing
        ):
            result.issues.append(
                ValidationIssueResult(
                    field="evidence_text",
                    issue_type=ValidationIssueType.FABRICATED,
                    message="Classifier evidence does not appear in the original feedback.",
                )
            )
        result.validation_status = ValidationStatus.REJECTED
        result.requires_human_review = True
        result.validation_summary = (
            "The classifier contains an unsupported category or evidence excerpt."
        )

    def _enforce_human_review(self, analysis: FeedbackAnalysis, result: ValidationResult) -> None:
        uncertain_issue_types = {
            ValidationIssueType.UNSUPPORTED,
            ValidationIssueType.INVALID,
            ValidationIssueType.MISSING,
            ValidationIssueType.INCONSISTENT,
            ValidationIssueType.FABRICATED,
            ValidationIssueType.AMBIGUOUS,
            ValidationIssueType.UNREASONABLE,
        }
        if (
            result.validation_status != ValidationStatus.APPROVED
            or result.overall_confidence < self.review_threshold
            or self._materially_disagrees(analysis, result)
            or any(issue.issue_type in uncertain_issue_types for issue in result.issues)
        ):
            result.requires_human_review = True

    @staticmethod
    def _materially_disagrees(analysis: FeedbackAnalysis, result: ValidationResult) -> bool:
        classifier_sentiment = "Mixed" if analysis.is_mixed else analysis.sentiment
        classifier_categories = {aspect.category for aspect in analysis.aspects}
        return (
            result.validated_sentiment.value != classifier_sentiment
            or result.validated_severity.value != analysis.severity
            or set(result.validated_categories) != classifier_categories
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()
