# Financial Tool Contract

The agentic layer does not implement financial tools. A configured provider supplies LangChain
`BaseTool` objects and agent-level `ToolMetadata`.

## Provider

Set `AGENTIC_TOOL_PROVIDER=package.module:function`. The callable must return one of:

- `ToolBundle(tools=(...), metadata=(...))`;
- `(tools, metadata)`;
- tools only, with matching entries in `agentic/config/tools.yaml`.

Every tool must have a unique stable name and a strict Pydantic argument schema. User, tenant,
permission, and confirmation values must not be accepted as model-controlled arguments. The tool
implementation receives authoritative identity through its own trusted integration mechanism.

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
    required_scopes: [financial:write]
    requires_confirmation: true
    requires_receipt: true
    requires_owner_metadata: true
    idempotent: true
    max_calls_per_task: 2
```

Read tools may be retried according to `limits.yaml`. Write and financial-action tools default to
one attempt. All calls are scoped, audited, redacted, size-limited, and idempotency-protected by
the agent boundary.

