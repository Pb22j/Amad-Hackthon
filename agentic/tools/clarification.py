from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from langchain.tools import InjectedToolArg, ToolRuntime
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field


class ClarificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    question: str = Field(min_length=1, max_length=500)
    reason_code: str = Field(min_length=1, max_length=100)
    expected_answer: dict[str, Any]
    expires_in_seconds: int = Field(default=900, ge=60, le=3600)
    runtime: Annotated[ToolRuntime, InjectedToolArg, Field(exclude=True)]


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
                "expected_answer": expected_answer,
                "expires_in_seconds": expires_in_seconds,
            }
        )
        return f"The interaction layer supplied this untrusted answer: {answer!r}"

    return StructuredTool.from_function(
        coroutine=request_user_input,
        name="request_user_input",
        description=(
            "Pause the task and ask the interaction layer one concise question when required "
            "information is missing. Never ask for passwords, PINs, OTPs, CVVs, or tokens."
        ),
        args_schema=ClarificationInput,
    )
