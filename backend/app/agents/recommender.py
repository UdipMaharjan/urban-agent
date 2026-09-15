from ..schemas import RecommendationResult, RecommendationTrendInput
from ..services.llm import LLMInvalidResponseError
from .classifier import StructuredLLM


class RecommendationAgent:
    """Turns one deterministic trusted trend into a proposed business action."""

    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    def recommend(self, trend: RecommendationTrendInput) -> RecommendationResult:
        instructions = (
            "You are UrbanAgent's Business Recommendation Agent. Use only the supplied trusted "
            "trend metrics, evidence summaries, feedback IDs, and UrbanMart business context. "
            "Do not inspect or infer a wider dataset. Propose a practical operational improvement "
            "that is proportionate to the evidence and does not require major infrastructure when "
            "a simpler action is available. Reference a supplied business rule only when relevant. "
            "Do not invent policies, customer details, causes, approvals, implementation status, "
            "or outcomes. Preserve every supporting_feedback_id exactly and set evidence_count to "
            "their count. requires_management_approval must be true. The recommendation is a "
            "proposal only and must never claim it was approved or executed. Return only the typed "
            "structured object; do not include chain-of-thought."
        )
        result = self.llm.structured_response(
            instructions=instructions,
            input_text=trend.model_dump_json(),
            response_model=RecommendationResult,
        )
        self._validate_result(trend, result)
        return result

    @staticmethod
    def _validate_result(trend: RecommendationTrendInput, result: RecommendationResult) -> None:
        if result.category != trend.category:
            raise LLMInvalidResponseError("The recommendation changed the trend category.")
        if len(result.supporting_feedback_ids) != len(set(result.supporting_feedback_ids)):
            raise LLMInvalidResponseError(
                "The recommendation returned duplicate supporting feedback IDs."
            )
        if set(result.supporting_feedback_ids) != set(trend.supporting_feedback_ids):
            raise LLMInvalidResponseError(
                "The recommendation did not preserve the supporting feedback IDs."
            )
        if result.evidence_count != len(trend.supporting_feedback_ids):
            raise LLMInvalidResponseError(
                "Recommendation evidence_count does not match its supporting feedback IDs."
            )
        if not result.requires_management_approval:
            raise LLMInvalidResponseError(
                "Recommendations must require explicit management approval."
            )
