# RepairFlow — autonomous repair coordination

**Status:** researched architectural specification; no application implemented.  
**Research snapshot:** 19 September 2026. **Target:** one-day {Tech: Europe} Agentic AI Hack, London.

RepairFlow maintains a repair case across calls, appointments and contractor reports. It interprets new evidence, proposes the next action, executes only policy-approved actions, and waits durably for the next real-world event.

The buyer hypothesis is a UK residential letting agency's head of property management. The operator supervises exceptions; residents and approved contractors supply information. The strongest published operational evidence comes from English social housing, which is adjacent to, but not identical to, the initial buyer segment. See [business research](docs/02_BUSINESS_PROBLEM_RESEARCH.md).

## Hero demonstration

A roof visit cannot proceed without scaffolding. The coordinator interprets the contractor's report, preserves the original unresolved issue, creates a prerequisite, and blocks roofing. A manager approves the simulated scaffolding commitment. When installation and access handover are reported complete, the original roofing order becomes actionable and is rebooked. Tenant confirmation and all required follow-on work gate resolution.

The demo compresses days into minutes. Contractor organisations, calendars, bookings and physical work are **SIMULATED IN MVP**. Gemini decisions and one ElevenLabs browser voice conversation are intended to be live. Tavily can supply real, cited contractor candidates, which remain unverified and cannot be booked automatically.

The live-call acceptance gate requires playable recorded audio, the full speaker-labelled transcript and a structured outcome linked to the case. Tavily queries and returned evidence also remain inspectable.

## Recommended stack

| Responsibility | Choice |
|---|---|
| UI | React + TypeScript + Vite; Tailwind/shadcn/ui; React Flow |
| API and worker | Python 3.12, FastAPI, one Uvicorn process |
| Reasoning framework | Pydantic AI `Agent`, typed tools/dependencies/output |
| Reasoning model | `gemini-3.8-flash`; explicit access/capability smoke test |
| Voice | ElevenLabs Agents browser session; telephony is stretch scope |
| Research | Tavily Search; bounded Extract only if needed |
| State | SQLite on persistent local disk, SQLAlchemy 2.0, Pydantic v2 |
| Resumption | Database jobs and action ledger; one application worker |
| Updates | Versioned HTTP polling, not SSE |
| Diagnostics | Structured local logs; optional redacted Logfire traces |
| Demo deployment | FastAPI serves the built UI; HTTPS tunnel for webhooks |
| Excluded from MVP | Modal, Conduct integration, Graph runtime, multiple operational agents |

This is an architectural choice, not an assertion that sponsors require this stack. Official current model/provider evidence is in [Gemini integration](docs/13_GEMINI_INTEGRATION.md).

## Documentation index

| Read | Document |
|---|---|
| Event and product | [00 Hackathon](docs/00_HACKATHON_CONTEXT.md), [01 Vision](docs/01_PRODUCT_VISION.md) |
| Evidence and competition | [02 Business](docs/02_BUSINESS_PROBLEM_RESEARCH.md), [03 Competitors](docs/03_COMPETITOR_RESEARCH.md) |
| Scope and topology | [04 MVP](docs/04_MVP_SCOPE.md), [05 Architecture](docs/05_SYSTEM_ARCHITECTURE.md) |
| Domain contracts | [06 Models](docs/06_DOMAIN_MODEL.md), [07 State machine](docs/07_CASE_STATE_MACHINE.md) |
| Agent implementation | [08 Agent](docs/08_AGENT_ARCHITECTURE.md), [09 Pydantic AI](docs/09_PYDANTIC_AI_DESIGN.md), [10 Tools](docs/10_TOOL_CATALOG.md) |
| Integrations | [11 ElevenLabs](docs/11_ELEVENLABS_INTEGRATION.md), [12 Tavily](docs/12_TAVILY_INTEGRATION.md), [13 Gemini](docs/13_GEMINI_INTEGRATION.md) |
| Sponsor assessments | [14 Modal](docs/14_MODAL_ASSESSMENT.md), [15 Conduct](docs/15_CONDUCT_ASSESSMENT.md) |
| Interfaces and storage | [16 API](docs/16_API_AND_WEBHOOK_DESIGN.md), [17 Database](docs/17_DATABASE_DESIGN.md) |
| Experience and boundaries | [18 UI](docs/18_FRONTEND_UX.md), [19 Safety](docs/19_SAFETY_AND_ESCALATION.md) |
| Execution | [20 Demo](docs/20_DEMO_SCRIPT.md), [21 Build plan](docs/21_IMPLEMENTATION_PLAN.md), [22 Testing](docs/22_TESTING_STRATEGY.md) |
| Due diligence | [23 Risks](docs/23_RISKS_AND_OPEN_QUESTIONS.md), [24 Sources](docs/24_RESEARCH_SOURCES.md) |
| Review | [25 Questions answered](docs/25_RESEARCH_QUESTIONS_ANSWERED.md), [26 Consistency review](docs/26_SPECIFICATION_REVIEW.md) |

## MVP acceptance

One persistent case completes the unexpected dependency loop without direct UI status editing. Duplicate delivery causes no duplicate commitment. A backend restart while roofing is blocked preserves the case and allows continuation. A gas/electrical-danger variant pauses automation. The UI identifies evidence, proposed action, executed result and simulated activity separately.

## Start implementation later

Read [CLAUDE.md](CLAUDE.md), then give the coding agent [IMPLEMENTATION_PROMPT.md](prompts/IMPLEMENTATION_PROMPT.md). Begin with the tested dependency loop and a minimal visible UI; voice and web search come after that path works.

No runtime commands, deployed service, provider credentials, measured savings, or passing application tests are claimed by this documentation release.
