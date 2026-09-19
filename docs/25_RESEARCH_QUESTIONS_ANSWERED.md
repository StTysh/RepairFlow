# 25 — Answers to the requested research questions

This is the navigation and conclusion layer. Evidence and exact interfaces live in the linked canonical documents.

| # | Question | Answer / source of detail |
|---|---|---|
| 1 | Does the problem exist? | Yes: repair timeliness and documented coordination/dependency failures; not all delay is software-addressable. [02](02_BUSINESS_PROBLEM_RESEARCH.md) |
| 2 | Who buys/uses it? | Initial buyer hypothesis: English letting-agency head of property management; managers supervise, tenants/contractors interact. Willingness to pay unvalidated. [01](01_PRODUCT_VISION.md) |
| 3 | How handled today? | Repair desk/manager plus portals, work orders, preferred suppliers, calls/messages, approvals and contractor reports. [02](02_BUSINESS_PROBLEM_RESEARCH.md) |
| 4 | Closest products? | askporter, Fixflo/Aidenn, Property Meld/MAX/Mezo, AppFolio Maintenance Performer, EliseAI and Latchel; platform incumbents also overlap. [03](03_COMPETITOR_RESEARCH.md) |
| 5 | Genuine differentiation? | A demonstrable, inspectable dependency-recovery loop; uniqueness versus competitors is unproven. [01](01_PRODUCT_VISION.md), [03](03_COMPETITOR_RESEARCH.md) |
| 6 | Sufficiently agentic? | Yes as a bounded design: interpret unexpected evidence, select actions, act, wait durably, replan. Event eligibility still depends on unpublished rules. [08](08_AGENT_ARCHITECTURE.md) |
| 7 | What needs an LLM? | Free-text interpretation, missing questions, inferred prerequisites and next-action recommendation. [08](08_AGENT_ARCHITECTURE.md), [13](13_GEMINI_INTEGRATION.md) |
| 8 | What stays deterministic? | Identity, authority, transitions, DAG checks, money, booking truth, persistence, idempotency and closure. [07](07_CASE_STATE_MACHINE.md), [10](10_TOOL_CATALOG.md) |
| 9 | Pydantic AI role? | Typed Agent, RunContext, scoped tools, ToolOutput, validation/retry and optional traces/evals. Graph/Harness excluded. [09](09_PYDANTIC_AI_DESIGN.md) |
| 10 | Gemini role? | Produce evidence-linked ActionProposal from each fresh case snapshot; exact selected model gemini-3.8-flash with access smoke test. [13](13_GEMINI_INTEGRATION.md) |
| 11 | ElevenLabs role? | Voice conversation and in-call observations, full transcript, actual recording and post-call evidence. Backend retains operational authority. [11](11_ELEVENLABS_INTEGRATION.md) |
| 12 | Tavily role? | Logged, source-linked web discovery; no availability, vetting or booking guarantee. [12](12_TAVILY_INTEGRATION.md) |
| 13 | Modal useful? | Not for the selected small I/O workload; optional later batch evaluation/compute. [14](14_MODAL_ASSESSMENT.md) |
| 14 | Conduct useful? | No justified integration found; enterprise-software offering and co-host role do not imply a repair API. [15](15_CONDUCT_ASSESSMENT.md) |
| 15 | One or several agents? | One operational coordinator; constrained ElevenLabs conversation is an interface, not another planning authority. [08](08_AGENT_ARCHITECTURE.md) |
| 16 | Persist across days? | SQL rows, events, jobs/actions and recorded evidence; process restart recovery on persistent disk. Always-on hosting required for real availability. [17](17_DATABASE_DESIGN.md) |
| 17 | Dependencies? | Explicit per-case DAG table, prerequisite → dependent, all incoming edges required; removal obligation included. [07](07_CASE_STATE_MACHINE.md) |
| 18 | Resume on events? | Ingress transaction writes event/job; worker loads latest snapshot; bounded run executes guarded proposal. [05](05_SYSTEM_ARCHITECTURE.md), [17](17_DATABASE_DESIGN.md) |
| 19 | Honest booking MVP? | Persistent MockBookingConnector with fictional approved suppliers, explicit SIMULATED outcomes. [10](10_TOOL_CATALOG.md) |
| 20 | Real versus mock? | Real Gemini, recorded browser ElevenLabs and optional Tavily; simulated calendars, bookings, visits, scaffold work and optional follow-up. [04](04_MVP_SCOPE.md) |
| 21 | Serious risks? | Missed hazard, false closure, duplicate/unknown commitment, wrong-case evidence, privacy, unverified suppliers and weak commercial novelty. [19](19_SAFETY_AND_ESCALATION.md), [23](23_RISKS_AND_OPEN_QUESTIONS.md) |
| 22 | Human escalation? | Hazards, critical uncertainty, vulnerability concerns, missing authority, scaffold scope/handover, contradictions, no supplier and unknown effect. [19](19_SAFETY_AND_ESCALATION.md) |
| 23 | One-day feasible scope? | One case, one issue, bounded agent, three linked work orders, one recorded browser call, simulated world and minimal graph. Ambitious but scoped. [04](04_MVP_SCOPE.md), [21](21_IMPLEMENTATION_PLAN.md) |
| 24 | What gets cut? | PSTN provisioning, real procurement/outreach, payments, multi-tenancy, multiple agents, cloud workflow platforms, broad multimodality. [04](04_MVP_SCOPE.md) |
| 25 | Strongest demo? | Safe roof report unexpectedly requires scaffold; graph changes, approval, accepted completion, original roof auto-resumes, truthful closure. [20](20_DEMO_SCRIPT.md) |
| 26 | Which event tech to show? | Actual Gemini reasoning and meaningful Pydantic AI typed execution. Modal/Conduct only if useful and rules justify them. [00](00_HACKATHON_CONTEXT.md), [20](20_DEMO_SCRIPT.md) |
| 27 | Sponsor prizes/incentives? | UNKNOWN; none invented. Organizer confirmation required. [00](00_HACKATHON_CONTEXT.md) |
| 28 | Under-one-minute architecture pitch? | Voice evidence → durable case → typed model proposal → policy/transaction → action → new event; scripted wording provided. [20](20_DEMO_SCRIPT.md) |
| 29 | Evidence of commercial value? | Established repair-management category and documented operational pain; this product's ROI and demand require measurement. [02](02_BUSINESS_PROBLEM_RESEARCH.md) |
| 30 | Likely technical questions? | Durability, duplicate effects, novel versus scripted branch, safety authority, booking reality, recorded-call proof and competitor overlap. Answers in [20](20_DEMO_SCRIPT.md) |
| 31 | Will the application see and record the actual call? | Required implementation gate: provider audio saving, transcript webhook/reconciliation, audio retrieval, case mapping, playback and caller-informed next action. Tavily logs research separately. Not yet implemented or tested. [11](11_ELEVENLABS_INTEGRATION.md), [22](22_TESTING_STRATEGY.md) |
