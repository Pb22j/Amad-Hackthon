# Financial Tool Contract

The repository includes a SQLite-backed demo provider, while the agent boundary also accepts
external LangChain `BaseTool` objects and agent-level `ToolMetadata`.

## Default tools package

The application automatically imports `agentic.tools` and reads its `TOOLS` or `tools` list. It
also accepts a `get_tools()` or `get_tool_bundle()` factory. This list defines the complete set of
financial functionalities visible to the agent.

## Provider override

Set `AGENTIC_TOOL_PROVIDER=package.module:attribute` to override the default package. The exported
value or callable result must be one of:

- `ToolBundle(tools=(...), metadata=(...))`;
- `(tools, metadata)`;
- tools only, with matching entries in `agentic/config/tools.yaml`.

Every tool must have a unique stable name and a strict Pydantic argument schema. User, tenant,
permission, confirmation, and OTP values must not be accepted as model-controlled arguments. The
guard binds authoritative request identity through an async-safe runtime context immediately around
each invocation.

## Result envelope

Every tool returns an object accepted by `ToolResult`:

```json
{
  "status": "completed | failed | pending | unknown",
  "summary": "Short, safe summary",
  "data": {},
  "user_id": "resource owner",
  "tenant_id": "resource tenant",
  "receipt_id": "required for completed configured financial actions",
  "operation_id": "provider operation identifier",
  "error_code": "stable safe error code"
}
```

Sensitive results must contain owner metadata. Financial actions configured with
`requires_receipt` must return an authoritative receipt when completed. A timed-out write must
return or expose a way to query `pending`/`unknown`; it must not invite a blind retry.

## Agent-level metadata

```yaml
tools:
  transfer_funds:
    risk: financial_action
    intents: [money_transfer]
    explicit_user_fields: [destination, amount]
    required_scopes: [financial:write]
    requires_confirmation: true
    requires_receipt: true
    requires_owner_metadata: true
    idempotent: true
    max_calls_per_task: 2
```

Read tools may be retried according to `limits.yaml`. Write and financial-action tools default to
one attempt. All calls are scoped, audited, redacted, size-limited, and idempotency-protected by
the agent boundary. Financial confirmation requires both the exact signed authorization token and
the dedicated demo OTP (`1111`). The OTP is never part of tool arguments, graph state, or audit data.

`intents` is also a least-privilege boundary. After deterministic classification, external tools
whose metadata does not match the classified intent are removed from the model request. Every
production tool should declare its supported intents; an empty value is reserved for deliberately
global capabilities during migration.

`explicit_user_fields` prevents the model from inventing a counterparty or resource identifier.
The guarded wrapper requires each listed value to be evidenced in the original authenticated
request or a signed clarification answer persisted for that task. Otherwise it emits a
clarification interrupt, validates the interaction layer's answer through the original Pydantic
tool schema, and calculates confirmation only after that answer.
