"""Deterministic security wrapper applied to every external financial tool.

The wrapper is deliberately outside the model loop. It derives identity from
runtime context, validates scopes and exact confirmation, deduplicates writes,
records audit data, constrains retries, and verifies ownership and receipts on
the returned result before the model can observe it.
"""

import hashlib
import json
import asyncio
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from langchain.tools import InjectedToolArg, ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import async_sessionmaker
from pydantic import BaseModel, ConfigDict, Field

from agentic.config.loader import AppConfig
from agentic.persistence.models import ToolExecutionRow
from agentic.persistence.repositories.authorizations import AuthorizationRepository
from agentic.persistence.repositories.audit import AuditRepository
from agentic.persistence.repositories.executions import ToolExecutionRepository
from agentic.security.confirmation import ConfirmationSigner, arguments_hash
from agentic.security.identity import AuthContext
from agentic.security.redaction import redact
from agentic.tools.metadata import ToolMetadata, ToolResult
from agentic.tools.runtime_identity import bind_tool_identity
from agentic.telemetry.metrics import TOOL_CALLS, TOOL_DURATION


class ToolGuardError(RuntimeError):
    """Safe boundary failure caused by an invalid tool call or result."""

    pass


@dataclass(slots=True)
class AgentRuntimeContext:
    """Trusted per-task values injected by LangGraph, never by model arguments."""

    auth: AuthContext
    task_id: str
    session_factory: async_sessionmaker
    config: AppConfig
    confirmation_signer: ConfirmationSigner
    initial_authorization_token: str | None = None
    otp_verified: bool = False
    original_request: str = ""
    explicit_user_values: tuple[Any, ...] = ()


def _idempotency_key(task_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
    """Bind a repeatable execution key to task, tool, and canonical arguments."""

    material = f"{task_id}:{tool_name}:{arguments_hash(arguments)}"
    return hashlib.sha256(material.encode()).hexdigest()


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _argument_is_explicit(
    value: Any, request: str, explicit_user_values: tuple[Any, ...]
) -> bool:
    """Check that a protected model argument appears in authenticated text."""

    evidence = (request, *(str(item) for item in explicit_user_values))
    if isinstance(value, (list, tuple, set)):
        return bool(value) and all(
            _argument_is_explicit(item, request, explicit_user_values) for item in value
        )
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            expected = Decimal(str(value))
        except InvalidOperation:
            return False
        for item in evidence:
            for token in re.findall(r"(?<!\w)\d+(?:[.,]\d+)?", item):
                try:
                    if Decimal(token.replace(",", ".")) == expected:
                        return True
                except InvalidOperation:
                    continue
        return False
    rendered = str(value).strip().casefold()
    return bool(rendered) and any(rendered in item.casefold() for item in evidence)


class GuardedToolFactory:
    """Turn an external tool into the only callable form exposed to the model."""

    def __init__(self, context_type: type[AgentRuntimeContext] = AgentRuntimeContext) -> None:
        self.context_type = context_type

    def wrap(self, external_tool: BaseTool, metadata: ToolMetadata) -> StructuredTool:
        """Return a tool with injected runtime context and deterministic guards."""

        if external_tool.name != metadata.name:
            raise ValueError("tool metadata name must match the external tool")
        args_schema = external_tool.args_schema
        if args_schema is None:
            raise ValueError(f"tool {external_tool.name!r} must declare an argument schema")
        if not isinstance(args_schema, type) or not issubclass(args_schema, BaseModel):
            raise ValueError(f"tool {external_tool.name!r} must use a Pydantic argument schema")
        guarded_args_schema = type(
            f"Guarded{args_schema.__name__}",
            (args_schema,),
            {
                "model_config": ConfigDict(
                    **dict(args_schema.model_config), arbitrary_types_allowed=True
                ),
                "__annotations__": {
                    "runtime": Annotated[
                        ToolRuntime, InjectedToolArg, Field(exclude=True)
                    ],
                },
                "runtime": ...,
            },
        )

        async def guarded(runtime: ToolRuntime, **arguments: Any) -> str:
            context: AgentRuntimeContext = runtime.context

            # Stage 1: authorize using server-injected identity and scopes.
            context.auth.require_scopes(metadata.required_scopes)

            # Resource identifiers and counterparties must come from the user,
            # not a model default. Missing evidence becomes an interaction-layer
            # clarification before idempotency or confirmation is calculated.
            for field_name in sorted(metadata.explicit_user_fields):
                if field_name not in arguments:
                    raise ToolGuardError(
                        f"tool argument schema lacks explicit field {field_name!r}"
                    )
                if not _argument_is_explicit(
                    arguments[field_name],
                    context.original_request,
                    context.explicit_user_values,
                ):
                    arguments[field_name] = interrupt(
                        {
                            "kind": "clarification",
                            "clarification_id": str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"{context.task_id}:{metadata.name}:{field_name}",
                                )
                            ),
                            "question": f"What value should be used for {field_name}?",
                            "reason_code": f"missing_explicit_{field_name}",
                            "expected_answer": {"type": "string", "field": field_name},
                            "expires_in_seconds": 900,
                        }
                    )
            # Answers returned through interrupts cross an untyped HTTP boundary;
            # re-run the original strict schema before using or hashing them.
            arguments = args_schema.model_validate(arguments).model_dump()
            tool_call_id = runtime.tool_call_id or hashlib.sha256(
                json.dumps(arguments, sort_keys=True, default=str).encode()
            ).hexdigest()[:24]
            key = _idempotency_key(context.task_id, metadata.name, arguments)

            # Stage 2: converge retries/replays before any external side effect.
            async with context.session_factory() as session:
                executions = ToolExecutionRepository(session)
                existing = await executions.get_by_idempotency(
                    tenant_id=context.auth.tenant_id, idempotency_key=key
                )
                if existing is not None:
                    if existing.status == "completed":
                        return json.dumps(existing.result or {}, ensure_ascii=False)
                    return json.dumps(
                        {
                            "status": "unknown",
                            "summary": "An execution with this idempotency key is already in progress.",
                            "operation_id": existing.operation_id,
                        }
                    )

            token = context.initial_authorization_token
            if metadata.requires_confirmation:
                # The interrupt is presented by the interaction layer. Its
                # signed response is bound to these exact normalized arguments.
                if not token:
                    token = interrupt(
                        {
                            "kind": "confirmation",
                            "tool_name": metadata.name,
                            "arguments": redact(arguments),
                            "arguments_hash": arguments_hash(arguments),
                            "expires_in_seconds": 300,
                        }
                    )
                if not context.otp_verified:
                    raise ToolGuardError("financial confirmation requires verified demo OTP")
                claims = context.confirmation_signer.verify(
                    str(token),
                    auth=context.auth,
                    task_id=context.task_id,
                    tool_name=metadata.name,
                    arguments=arguments,
                )
            else:
                claims = None

            # Stage 3: consume a single-use authorization and durably record the
            # execution before calling the teammate-owned implementation.
            async with context.session_factory() as session:
                if claims:
                    await AuthorizationRepository(session).consume(claims)
                await AuditRepository(session).record(
                    task_id=context.task_id,
                    tenant_id=context.auth.tenant_id,
                    user_id=context.auth.user_id,
                    category="tool_authorization",
                    decision="allowed",
                    reason_code="scopes_and_confirmation_valid",
                    details={"tool_name": metadata.name, "arguments_hash": arguments_hash(arguments)},
                )
                execution, created = await ToolExecutionRepository(session).start(
                    task_id=context.task_id,
                    tenant_id=context.auth.tenant_id,
                    tool_call_id=tool_call_id,
                    tool_name=metadata.name,
                    arguments=redact(arguments),
                    idempotency_key=key,
                )
                await session.commit()
                if not created:
                    if execution.status == "completed":
                        return json.dumps(execution.result or {}, ensure_ascii=False)
                    return json.dumps(
                        {
                            "status": "unknown",
                            "summary": "An execution with this idempotency key is already in progress.",
                            "operation_id": execution.operation_id,
                        }
                    )
                execution_id = execution.id

            try:
                tool_started = time.monotonic()
                # Reads may retry transient failures. Writes follow the stricter
                # configured budget and rely on idempotency, never model judgment.
                attempts = (
                    context.config.limits.retries.read_tool_attempts
                    if metadata.risk.value in {"read", "sensitive_read"}
                    else context.config.limits.retries.write_tool_attempts
                )
                last_error: Exception | None = None
                for attempt in range(attempts):
                    try:
                        with bind_tool_identity(
                            user_id=context.auth.user_id,
                            tenant_id=context.auth.tenant_id,
                        ):
                            raw_result = await external_tool.ainvoke(arguments)
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt + 1 >= attempts:
                            raise
                        await asyncio.sleep(0.05 * (2**attempt))
                else:  # pragma: no cover - loop always exits by break or raise
                    raise ToolGuardError("tool retry loop ended unexpectedly") from last_error
                result = ToolResult.model_validate(raw_result)
                # Stage 4: treat even internal tool output as untrusted data.
                self._validate_result(result, metadata, context.auth)
                safe_result = redact(result.model_dump(mode="json"))
                if _serialized_size(safe_result) > context.config.limits.task.max_tool_result_bytes:
                    raise ToolGuardError("tool result exceeds the configured size limit")
            except Exception as exc:
                TOOL_CALLS.labels(tool=metadata.name, outcome="failed").inc()
                async with context.session_factory() as session:
                    row = await session.get(ToolExecutionRow, execution_id)
                    if row is not None:
                        await ToolExecutionRepository(session).complete(
                            row,
                            status="failed",
                            result={"status": "failed", "summary": "Tool execution failed safely."},
                            error_code=type(exc).__name__,
                        )
                        await session.commit()
                raise

            async with context.session_factory() as session:
                row = await session.get(ToolExecutionRow, execution_id)
                if row is None:
                    raise ToolGuardError("tool execution audit record disappeared")
                await ToolExecutionRepository(session).complete(
                    row,
                    status=result.status,
                    result=safe_result,
                    receipt_id=result.receipt_id,
                    operation_id=result.operation_id,
                    error_code=result.error_code,
                )
                await session.commit()
            TOOL_CALLS.labels(tool=metadata.name, outcome=result.status).inc()
            TOOL_DURATION.labels(tool=metadata.name).observe(time.monotonic() - tool_started)
            return json.dumps(safe_result, ensure_ascii=False)

        return StructuredTool.from_function(
            coroutine=guarded,
            name=external_tool.name,
            description=external_tool.description,
            args_schema=guarded_args_schema,
        )

    @staticmethod
    def _validate_result(
        result: ToolResult, metadata: ToolMetadata, auth: AuthContext
    ) -> None:
        """Reject cross-principal data and unsupported financial success claims."""

        if metadata.requires_owner_metadata:
            if result.user_id is None or result.tenant_id is None:
                raise ToolGuardError("tool result lacks required ownership metadata")
            if result.user_id != auth.user_id or result.tenant_id != auth.tenant_id:
                raise PermissionError("tool returned data for a different user or tenant")
        if metadata.requires_receipt and result.status == "completed" and not result.receipt_id:
            raise ToolGuardError("completed financial action lacks an authoritative receipt")
