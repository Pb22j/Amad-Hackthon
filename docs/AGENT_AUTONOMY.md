# Backend agent autonomy

The backend agent is designed to do as much safe work as possible without turning missing context
into unnecessary questions. Autonomy is bounded by deterministic identity, authorization,
confirmation, ownership, receipt, and output-grounding controls.

## Evidence hierarchy

1. The current request and signed prior-user statements establish the user's requested goal and
   explicitly supplied action arguments.
2. Verified scoped memory may provide low-sensitivity preferences, but it cannot establish live
   balances or silently authorize a financial action.
3. Financial tools establish current account, transaction, bill, beneficiary, investment, and
   execution facts.
4. Intent classification is an advisory routing decision. It is never factual evidence.

The agent resolves a pronoun, alias, follow-up, or repeated constraint only when the available
evidence leaves one reasonable interpretation. Otherwise it asks one field-specific question.

## Execution infrastructure

- Context-aware classification receives provenance-labelled conversation evidence.
- Compound classification selects a primary intent and up to four additional independently
  requested intents, then exposes the union of only those capabilities.
- The highest-risk part controls request risk; any prohibited part rejects the complete request.
- A trusted task brief gives the inner agent its selected capabilities, evidence rules, and bounded
  execution protocol on every model call.
- Low-confidence recognized requests remain in the reasoning path so the agent can use context,
  inspect capability schemas, or clarify. Only genuinely unknown goals use generic support.
- Prior-user evidence is encrypted with the task and restored after clarification or confirmation,
  so a resume does not lose the facts needed for safe inference.
- Tool and model budgets bound autonomous work, and duplicated reads are discouraged in the task
  brief. External tool wrappers continue to enforce least privilege and exact user provenance.

## Advisory autonomy

Decision-support requests use a separate financial-advisor sub-agent. It can retrieve the user's
available authenticated read data across financial domains, use deterministic analysis for derived
figures, compare options, and recommend one primary solution with trade-offs and user-controlled
next steps.

This sub-agent has no state-changing capabilities. The policy admits only `read` and
`sensitive_read` metadata, excludes any capability requiring confirmation or a receipt, and rejects
reports that claim an executed action or return a receipt. A request that mixes advice with an
instruction to act remains advisory-only; execution requires a later explicit request routed to the
regular guarded action agent.

## Non-negotiable limits

The agent cannot infer identity, scopes, confirmation, live financial state, action success, or
receipt identifiers. Those values must come from authenticated runtime context or authoritative
tool execution. Ambiguity affecting money, counterparty, account, quantity, or destination still
requires explicit evidence or a clarification.
