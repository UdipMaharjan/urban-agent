from typing import TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    OpenAI,
    OpenAIError,
)
from pydantic import BaseModel, ValidationError

from ..config import Settings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LLMServiceError(RuntimeError):
    pass


class LLMTimeoutError(LLMServiceError):
    pass


class LLMInvalidResponseError(LLMServiceError):
    pass


class OpenAIService:
    """One configured boundary for OpenAI Responses API calls."""

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.")
        if not settings.openai_model:
            raise LLMServiceError("OPENAI_MODEL is not configured.")
        self.model = settings.openai_model
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

    def structured_response(
        self,
        *,
        instructions: str,
        input_text: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "developer", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
                text_format=response_model,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("The OpenAI request timed out.") from exc
        except (ContentFilterFinishReasonError, LengthFinishReasonError) as exc:
            raise LLMInvalidResponseError(
                "OpenAI returned an incomplete structured response."
            ) from exc
        except (APIConnectionError, APIStatusError) as exc:
            raise LLMServiceError("The OpenAI request failed.") from exc
        except ValidationError as exc:
            raise LLMInvalidResponseError(
                "OpenAI returned an invalid structured response."
            ) from exc
        except OpenAIError as exc:
            raise LLMServiceError("The OpenAI request failed.") from exc

        parsed = response.output_parsed
        if parsed is None:
            raise LLMInvalidResponseError(
                "OpenAI returned no parsed output; the response may be incomplete or refused."
            )
        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise LLMInvalidResponseError(
                "OpenAI returned an invalid structured response."
            ) from exc
