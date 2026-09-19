# 09 — Meaningful Pydantic AI design

## Interpretation of the framework

The user's interpretation is substantially correct: the model selects tool calls and outputs; Python implements tools; Pydantic AI supplies the typed execution loop, dependency injection, validation and retry behavior. It does not supply repair-domain authority, a contractor network or an automatically durable case database. [Agent documentation](https://pydantic.dev/docs/ai/core-concepts/agent/).

Current documentation also includes capabilities, storage, realtime voice and an official separate Harness package. Do not design against a 2025-only view of the framework.

## Selected primitives

| Primitive | Application use | MVP |
|---|---|---|
| Agent | Reusable stateless coordinator definition; fresh run per wake | Yes |
| Pydantic models | Input/output/action/adapter validation | Yes |
| deps_type / RunContext | Case scope, read service, policy snapshot, clock and correlation IDs | Yes |
| @agent.tool | Case-scoped reads using injected context | Yes |
| @agent.tool_plain | Pure date/window helper if a model needs it; otherwise ordinary code | Usually unnecessary |
| ToolOutput | Structured ActionProposal via output tool, compatible with function-tool use | Yes |
| Output validator / ModelRetry | Reject malformed or unsupported proposals; bounded repair attempt | Yes |
| Toolsets | Small grouped read-tool set if convenient; no dynamic tool marketplace | Optional |
| Deferred tools / approval | Available but action-ledger approvals are clearer for this demo | No |
| Graph / GraphBuilder | Typed execution flow; distinct from dynamic work-order graph | No |
| Logfire | Redacted traces, timing, usage and tool failures | Should have if setup is quick |
| Pydantic Evals | Small scenario dataset; useful after deterministic tests | Optional |
| Harness capabilities | General memory/planning/subagents/runtime controls | Not required |
| Durable runtime integrations | Consider Temporal or DBOS when case scale warrants it | Post-hackathon |

Typed dependency behavior is documented in [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/); function schemas and contextual versus plain tools in [Function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/); grouping in [Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/).

## Concrete construction

Illustrative interface, to be checked against the installed locked SDK:

```python
coordinator = Agent(
    GoogleModel("gemini-3.8-flash", provider=GoogleProvider()),
    deps_type=CoordinatorDeps,
    output_type=ToolOutput(ActionProposal),
    instructions=COORDINATOR_INSTRUCTIONS,
)

@coordinator.tool
async def read_report(
    ctx: RunContext[CoordinatorDeps], report_id: UUID
) -> ContractorReport:
    return await ctx.deps.read_service.report_for_case(
        ctx.deps.case_id, report_id
    )
```

This is an interface example, not delivered application code.

`CoordinatorDeps`: `case_id, snapshot_version, run_id, read_service, policy_snapshot, clock`. No unrestricted DB session, API keys, mutation service, shell or arbitrary HTTP client is exposed to the model.

The caller invokes `await coordinator.run(..., deps=...)`, consumes `result.output`, then passes it to the separate action executor. Dependency injection is not authorization by itself; each read method enforces scope.

## Structured output decision

Use one ActionProposal model whose `action` field is a discriminated union. Prefer ToolOutput for the combined read-tool/proposal loop. Native structured output is suitable for extraction-only calls but does not remove application semantic validation. Provider/schema support must pass the phase-0 smoke test. [Output modes and retries](https://pydantic.dev/docs/ai/core-concepts/output/).

If the provider rejects the nested union schema, flatten to a list of typed output tools, one per NextAction variant, and wrap the resulting variant in the same envelope in trusted code. This is an allowed compatibility adaptation; API/domain semantics must remain unchanged and docs/26 must record it.

## Retry and budget policy

One output-validation retry; at most four model requests per run; at most three read-tool invocations; overall run timeout 25 seconds. These are starting budgets, not provider guarantees. Use the installed SDK's current usage/retry/timeout APIs and record the resolved settings.

Do not retry a dangerous or unauthorized action until the model says something more convenient. A policy rejection becomes a recorded outcome; a safety rejection becomes escalation. Transient provider retries use bounded backoff outside the domain transaction.

## Graph comparison

| Pattern | Fit |
|---|---|
| Deterministic application state machine | Best authority boundary and testability |
| Pydantic Graph | Useful when typed execution nodes themselves are complex; still requires storage/effect policies |
| LLM-driven entire workflow | Flexible but unsafe for lifecycle, payment and booking truth |
| Hybrid | Selected: typed semantic proposals plus deterministic state transitions |

Current Graph documentation uses GraphBuilder, steps, BaseNode and typed state/dependencies. It represents program control flow. The roof/scaffold relation is business data and must exist even when no graph run is active. [Pydantic Graph](https://pydantic.dev/docs/ai/graph/graph/).

## Durability and 2026 Harness assessment

Pydantic AI documents durable execution integrations including Temporal, DBOS, Prefect, Restate and AWS Lambda. Its documentation explicitly distinguishes durable execution from conversation storage. Our MVP instead persists each bounded run's inputs/results and resumes from domain state. [Durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/).

The official Harness adds composable capabilities for memory, planning, context management, subagents and execution environments, with its own 0.x compatibility policy. A repair coordinator does not need a coding-agent workspace, shell or general-purpose memory to remember work orders. Do not add Harness merely to satisfy “agentic.” [Harness](https://pydantic.dev/docs/ai/harness/).

## Observability and evaluation

Instrument model/tool latency and usage, run ID, case ID, proposal kind and policy result. Keep full caller transcript/audio in the case's protected records, not general logs. Optional Logfire exports must redact personal data and secrets. [Logfire integration](https://pydantic.dev/docs/ai/integrations/logfire/).

Use deterministic test models for orchestration tests and real Gemini for a small semantic evaluation. Pydantic Evals can organize examples and assertions, but is not a substitute for state-transition tests. [Unit testing](https://pydantic.dev/docs/ai/guides/testing/), [Evals](https://pydantic.dev/docs/ai/evals/evals/).

If Pydantic AI were removed, we would need to rebuild schema translation, tool dispatch, typed validation, retries and model observability. Its use here is central, not a decorative dependency.
