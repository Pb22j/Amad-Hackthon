"""Special interrupting tool for questions routed through the interaction layer."""

from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from langchain.tools import InjectedToolArg, ToolRuntime
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, field_validator


_ANSWER_TYPES = {"string", "number", "integer", "boolean"}
_SENSITIVE_FIELD = (
    "password",
    "passcode",
    "pin",
    "otp",
    "cvv",
    "token",
    "secret",
)


def normalize_expected_answer(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the small JSON-Schema subset understood by every interaction client."""

    answer_type = schema.get("type")
    if answer_type not in _ANSWER_TYPES:
        raise ValueError("expected_answer.type must be string, number, integer, or boolean")
    field_name = schema.get("field", "answer")
    if not isinstance(field_name, str) or not field_name.strip() or len(field_name) > 100:
        raise ValueError("expected_answer.field must be a short non-empty string")
    if any(term in field_name.lower() for term in _SENSITIVE_FIELD):
        raise ValueError("clarification fields must not request credentials or secrets")

    normalized: dict[str, Any] = {"type": answer_type, "field": field_name.strip()}
    for key in ("label", "description"):
        value = schema.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 300:
                raise ValueError(f"expected_answer.{key} must be a short non-empty string")
            normalized[key] = value.strip()

    choices = schema.get("enum")
    if choices is not None:
        if not isinstance(choices, list) or not 1 < len(choices) <= 20:
            raise ValueError("expected_answer.enum must contain between 2 and 20 choices")
        if any(isinstance(item, (dict, list)) or item is None for item in choices):
            raise ValueError("expected_answer.enum choices must be scalar values")
        normalized["enum"] = choices

    if answer_type == "string":
        normalized["minLength"] = int(schema.get("minLength", 1))
        normalized["maxLength"] = int(schema.get("maxLength", 500))
        if not 1 <= normalized["minLength"] <= normalized["maxLength"] <= 2_000:
            raise ValueError("expected_answer string length constraints are invalid")
    elif answer_type in {"number", "integer"}:
        for key in ("minimum", "maximum"):
            value = schema.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"expected_answer.{key} must be numeric")
                normalized[key] = value
        if normalized.get("minimum", float("-inf")) > normalized.get(
            "maximum", float("inf")
        ):
            raise ValueError("expected_answer numeric range is invalid")
    return normalized


class ClarificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    question: str = Field(min_length=1, max_length=500)
    reason_code: str = Field(min_length=1, max_length=100)
    expected_answer: dict[str, Any]
    expires_in_seconds: int = Field(default=900, ge=60, le=3600)
    runtime: Annotated[ToolRuntime, InjectedToolArg, Field(exclude=True)]

    @field_validator("expected_answer")
    @classmethod
    def validate_expected_answer(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_expected_answer(value)


def build_clarification_tool() -> StructuredTool:
    async def request_user_input(
        runtime: ToolRuntime,
        question: str,
        reason_code: str,
        expected_answer: dict[str, Any],
        expires_in_seconds: int,
    ) -> str:
        task_id = runtime.context.task_id
        tool_call_id = runtime.tool_call_id or "unknown"
        clarification_id = str(uuid5(NAMESPACE_URL, f"{task_id}:{tool_call_id}:clarification"))
        answer = interrupt(
            {
                "kind": "clarification",
                "clarification_id": clarification_id,
                "question": question,
                "reason_code": reason_code,
                "expected_answer": normalize_expected_answer(expected_answer),
                "expires_in_seconds": expires_in_seconds,
            }
        )
        return f"The interaction layer supplied this untrusted answer: {answer!r}"

    return StructuredTool.from_function(
        coroutine=request_user_input,
        name="request_user_input",
        description=(
            "Pause the task and ask the interaction layer one concise question when required "
            "information is missing. expected_answer must describe one scalar field using JSON "
            "Schema type string, number, integer, or boolean; include field and a user-friendly "
            "label, and use enum for a fixed choice list. Never ask for passwords, PINs, OTPs, "
            "CVVs, tokens, or secrets."
        ),
        args_schema=ClarificationInput,
    )
