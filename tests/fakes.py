from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agentic.policy.models import Intent, IntentClassification


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage]
    response_index: int = 0
    bound_tool_names: list[str] = Field(default_factory=list)
    seen_messages: list[list[Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"

    def bind_tools(self, tools: list[Any], **_: Any) -> "ScriptedChatModel":
        self.bound_tool_names = [getattr(tool, "name", "") for tool in tools]
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_messages.append(list(messages))
        del stop, run_manager, kwargs
        if self.response_index >= len(self.responses):
            raise AssertionError("scripted model ran out of responses")
        response = self.responses[self.response_index]
        self.response_index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class StaticClassifier:
    def __init__(
        self,
        intent: Intent,
        *,
        confidence: float = 1.0,
        related_intents: tuple[Intent, ...] = (),
        rationale_code: str = "test_fixture",
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.related_intents = related_intents
        self.rationale_code = rationale_code
        self.seen_inputs: list[Any] = []

    def with_structured_output(self, _: Any, **__: Any) -> "StaticClassifier":
        return self

    async def ainvoke(self, value: Any) -> IntentClassification:
        self.seen_inputs.append(value)
        return IntentClassification(
            intent=self.intent,
            related_intents=self.related_intents,
            confidence=self.confidence,
            rationale_code=self.rationale_code,
        )


def report_message(
    *,
    summary: str = "Done",
    status: str = "completed",
    receipt_ids: list[str] | None = None,
    result: dict[str, Any] | None = None,
    interaction_context: dict[str, Any] | None = None,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "AgentReport",
                "args": {
                    "status": status,
                    "summary": summary,
                    "actions": [],
                    "result": result or {},
                    "warnings": [],
                    "receipt_ids": receipt_ids or [],
                    "needs_follow_up": False,
                    "interaction_context": interaction_context
                    or {
                        "response_kind": "outcome",
                        "user_goal": "",
                        "key_facts": [],
                        "suggested_next_steps": [],
                    },
                },
                "id": "report-call",
                "type": "tool_call",
            }
        ],
    )
