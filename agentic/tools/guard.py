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
import unicodedata
from dataclasses import dataclass, field
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
    prior_user_statements: tuple[str, ...] = ()
    explicit_user_field_values: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    resuming_from_clarification: bool = False


def _idempotency_key(task_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
    """Bind a repeatable execution key to task, tool, and canonical arguments."""

    material = f"{task_id}:{tool_name}:{arguments_hash(arguments)}"
    return hashlib.sha256(material.encode()).hexdigest()


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _argument_is_explicit(
    value: Any,
    request: str,
    explicit_user_values: tuple[Any, ...],
    *,
    field_name: str | None = None,
    prior_user_statements: tuple[str, ...] = (),
) -> bool:
    """Check that a protected model argument appears in authenticated text."""

    evidence = (
        request,
        *prior_user_statements,
        *(str(item) for item in explicit_user_values),
    )
    if isinstance(value, (list, tuple, set)):
        return bool(value) and all(
            _argument_is_explicit(
                item,
                request,
                explicit_user_values,
                field_name=field_name,
                prior_user_statements=prior_user_statements,
            )
            for item in value
        )
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            expected = Decimal(str(value))
        except InvalidOperation:
            return False
        for item in evidence:
            # Preserve an explicit sign. Matching only the magnitude would let a
            # model turn a user-stated negative amount into a positive action.
            for token in re.findall(
                r"(?<!\w)[+-]?\d+(?:[,\u066c]\d+)*(?:[.\u066b]\d+)?(?!\w)",
                item,
            ):
                parsed = _parse_numeric_token(token)
                if parsed == expected:
                    return True
            for word_value in _word_number_values(item):
                if word_value == expected:
                    return True
        return False
    rendered = str(value).strip().casefold()
    if not rendered:
        return False
    exact = re.compile(rf"(?<!\w){re.escape(rendered)}(?!\w)", re.IGNORECASE)
    if any(exact.search(item) is not None for item in evidence):
        return True
    if field_name == "symbol":
        # Investment tools intentionally accept a small, server-owned alias
        # table. The model may choose the canonical symbol while the user says
        # the Arabic company name (for example, ARAMCO vs أرامكو). Treat only
        # those configured aliases as equivalent; arbitrary translations stay
        # blocked by the exact-provenance rule above.
        from agentic.tools.investments import SYMBOL_ALIASES, normalize_investment_symbol

        canonical = normalize_investment_symbol(rendered)
        for alias, alias_canonical in SYMBOL_ALIASES.items():
            if alias_canonical != canonical:
                continue
            alias_pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            if any(alias_pattern.search(item) is not None for item in evidence):
                return True
    return False


_ARABIC_FIELD_LABELS = {
    "account_reference": "مرجع الحساب",
    "amount": "المبلغ",
    "biller": "مقدم الخدمة",
    "benefit_account_number": "رقم حساب المستفيد",
    "destination": "الوجهة",
    "destination_account": "الحساب المستلم",
    "full_name_of_benefit_account": "اسم المستفيد الكامل",
    "gift_message": "رسالة الهدية",
    "last_four_digits": "آخر أربعة أرقام",
    "name": "الاسم",
    "participants": "المشاركون",
    "qatta_name": "اسم القطة",
    "quantity": "عدد الأسهم",
    "recipient": "المستلم",
    "short_name": "الاسم المختصر",
    "symbol": "رمز الاستثمار أو اسم الشركة",
    "total_amount": "المبلغ الإجمالي",
}


def _clarification_copy(field_name: str, request: str) -> tuple[str, str]:
    """Return a user-facing clarification question and label in request language."""

    if not re.search(r"[\u0600-\u06ff]", request):
        label = field_name.replace("_", " ").title()
        return f"What value should be used for {field_name}?", label
    label = _ARABIC_FIELD_LABELS.get(field_name, field_name.replace("_", " "))
    questions = {
        "amount": "ما المبلغ المطلوب؟",
        "destination": "إلى من تريد التحويل؟",
        "destination_account": "ما الحساب الذي تريد التحويل إليه؟",
        "quantity": "كم عدد الأسهم المطلوب؟",
        "symbol": "ما رمز الاستثمار أو اسم الشركة المطلوب؟",
    }
    return questions.get(field_name, f"ما القيمة المطلوبة لحقل {label}؟"), label


def _parse_numeric_token(token: str) -> Decimal | None:
    """Parse grouped/decimal Western or Arabic digits without changing magnitude."""

    normalized_chars: list[str] = []
    for character in token:
        if character.isdecimal():
            normalized_chars.append(str(unicodedata.decimal(character)))
        elif character == "\u066c":
            normalized_chars.append(",")
        elif character == "\u066b":
            normalized_chars.append(".")
        else:
            normalized_chars.append(character)
    normalized = "".join(normalized_chars)
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(",", "")
    elif "," in normalized:
        unsigned = normalized.lstrip("+-")
        groups = unsigned.split(",")
        if len(groups) > 2 or (len(groups) == 2 and len(groups[1]) == 3):
            normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


_EN_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_EN_SCALES = {
    "hundred": 100,
    "hundreds": 100,
    "thousand": 1_000,
    "thousands": 1_000,
    "million": 1_000_000,
    "millions": 1_000_000,
}

_AR_NUMBER_WORDS = {
    "صفر": 0,
    "واحد": 1,
    "واحدة": 1,
    "اثنان": 2,
    "اثنين": 2,
    "اثنتان": 2,
    "اثنتين": 2,
    "ثلاثة": 3,
    "ثلاث": 3,
    "أربعة": 4,
    "اربعة": 4,
    "أربع": 4,
    "اربع": 4,
    "خمسة": 5,
    "خمس": 5,
    "ستة": 6,
    "ست": 6,
    "سبعة": 7,
    "سبع": 7,
    "ثمانية": 8,
    "ثمان": 8,
    "تسعة": 9,
    "تسع": 9,
    "عشرة": 10,
    "عشر": 10,
    "عشرون": 20,
    "عشرين": 20,
    "ثلاثون": 30,
    "ثلاثين": 30,
    "أربعون": 40,
    "اربعون": 40,
    "أربعين": 40,
    "اربعين": 40,
    "خمسون": 50,
    "خمسين": 50,
    "ستون": 60,
    "ستين": 60,
    "سبعون": 70,
    "سبعين": 70,
    "ثمانون": 80,
    "ثمانين": 80,
    "تسعون": 90,
    "تسعين": 90,
    "مئة": 100,
    "مائة": 100,
    "مئتين": 200,
    "مائتين": 200,
    "ثلاثمائة": 300,
    "أربعمائة": 400,
    "اربعمائة": 400,
    "خمسمائة": 500,
    "ستمائة": 600,
    "سبعمائة": 700,
    "ثمانمائة": 800,
    "تسعمائة": 900,
    "ألفين": 2_000,
    "الفين": 2_000,
    "ألفان": 2_000,
    "الفان": 2_000,
    "مليونين": 2_000_000,
}
_AR_SCALES = {
    "ألف": 1_000,
    "الف": 1_000,
    "آلاف": 1_000,
    "الاف": 1_000,
    "مليون": 1_000_000,
    "ملايين": 1_000_000,
}


def _parse_english_number(words: list[str]) -> Decimal | None:
    """Parse a contiguous English number phrase, including casual plurals."""

    sign = 1
    if words and words[0] in {"minus", "negative"}:
        sign = -1
        words = words[1:]
    if not words:
        return None
    total = 0
    current = 0
    saw_number = False
    for word in words:
        if word == "and":
            continue
        if word in _EN_NUMBER_WORDS:
            current += _EN_NUMBER_WORDS[word]
            saw_number = True
            continue
        scale = _EN_SCALES.get(word)
        if scale is None:
            return None
        saw_number = True
        if scale == 100:
            current = (current or 1) * scale
        else:
            total += (current or 1) * scale
            current = 0
    return Decimal(sign * (total + current)) if saw_number else None


def _word_number_values(text: str) -> tuple[Decimal, ...]:
    """Extract signed word-number values without matching unrelated prose."""

    tokens = re.findall(r"[a-z]+", text.casefold().replace("-", " "))
    allowed = set(_EN_NUMBER_WORDS) | set(_EN_SCALES) | {"and", "minus", "negative"}
    values: list[Decimal] = []
    phrase: list[str] = []
    for token in (*tokens, ""):
        if token in allowed:
            phrase.append(token)
            continue
        if phrase:
            parsed = _parse_english_number(phrase)
            if parsed is not None:
                values.append(parsed)
            phrase = []
    arabic_tokens = re.findall(r"[\u0600-\u06ff]+", text)
    arabic_allowed = set(_AR_NUMBER_WORDS) | set(_AR_SCALES)
    arabic_phrase: list[str] = []
    for raw_token in (*arabic_tokens, ""):
        token = raw_token
        if token.startswith("و") and token[1:] in arabic_allowed:
            token = token[1:]
        if token in arabic_allowed:
            arabic_phrase.append(token)
            continue
        if arabic_phrase:
            total = 0
            current = 0
            for word in arabic_phrase:
                if word in _AR_NUMBER_WORDS:
                    current += _AR_NUMBER_WORDS[word]
                else:
                    scale = _AR_SCALES[word]
                    total += (current or 1) * scale
                    current = 0
            values.append(Decimal(total + current))
            arabic_phrase = []
    return tuple(values)


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
                    "runtime": Annotated[ToolRuntime, InjectedToolArg, Field(exclude=True)],
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
                    context.explicit_user_field_values.get(field_name, ()),
                    field_name=field_name,
                    prior_user_statements=context.prior_user_statements,
                ):
                    question, label = _clarification_copy(field_name, context.original_request)
                    arguments[field_name] = interrupt(
                        {
                            "kind": "clarification",
                            "clarification_id": str(
                                uuid5(
                                    NAMESPACE_URL,
                                    (
                                        f"{context.task_id}:{metadata.name}:{field_name}:"
                                        f"{runtime.tool_call_id or 'unknown'}"
                                    ),
                                )
                            ),
                            "question": question,
                            "reason_code": f"missing_explicit_{field_name}",
                            "expected_answer": {
                                "type": "string",
                                "field": field_name,
                                "label": label,
                                "minLength": 1,
                                "maxLength": 500,
                            },
                            "expires_in_seconds": 900,
                        }
                    )
            # Answers returned through interrupts cross an untyped HTTP boundary;
            # re-run the original strict schema before using or hashing them.
            arguments = args_schema.model_validate(arguments).model_dump()

            # This write has read-only eligibility checks that must pass before
            # a signed confirmation is shown. Users should never approve an
            # impossible transfer (unknown beneficiary, unavailable account,
            # insufficient funds, or exceeded limit).
            if metadata.name == "transfer_between_accounts":
                from agentic.tools.transfer_between_accounts import (
                    preflight_transfer_between_accounts,
                )

                with bind_tool_identity(
                    user_id=context.auth.user_id,
                    tenant_id=context.auth.tenant_id,
                ):
                    preflight = ToolResult.model_validate(
                        await preflight_transfer_between_accounts(**arguments)
                    )
                if preflight.status != "completed":
                    return preflight.model_dump_json()

            tool_call_id = (
                runtime.tool_call_id
                or hashlib.sha256(
                    json.dumps(arguments, sort_keys=True, default=str).encode()
                ).hexdigest()[:24]
            )
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
                # A clarification resume and confirmation interrupt cannot safely
                # share one LangGraph tool invocation: the prior answer can be
                # replayed into the next interrupt. Return control to the model
                # once, then let it repeat the exact normalized call so the
                # confirmation starts in a fresh invocation.
                if context.resuming_from_clarification:
                    context.resuming_from_clarification = False
                    return json.dumps(
                        {
                            "status": "input_received",
                            "summary": "The missing information was received. Repeat this exact tool call once to continue.",
                            "arguments": redact(arguments),
                        },
                        ensure_ascii=False,
                    )
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
                    details={
                        "tool_name": metadata.name,
                        "arguments_hash": arguments_hash(arguments),
                    },
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
    def _validate_result(result: ToolResult, metadata: ToolMetadata, auth: AuthContext) -> None:
        """Reject cross-principal data and unsupported financial success claims."""

        if metadata.requires_owner_metadata:
            if result.user_id is None or result.tenant_id is None:
                raise ToolGuardError("tool result lacks required ownership metadata")
            if result.user_id != auth.user_id or result.tenant_id != auth.tenant_id:
                raise PermissionError("tool returned data for a different user or tenant")
        if metadata.requires_receipt and result.status == "completed" and not result.receipt_id:
            raise ToolGuardError("completed financial action lacks an authoritative receipt")
