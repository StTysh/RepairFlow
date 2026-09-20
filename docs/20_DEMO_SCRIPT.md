# 20 — Four-to-five-minute demonstration

> **Superseded (2026-09-20).** This is the rehearsal script for the
> retired hackathon demo. Every control it depends on — Play demo, Reset
> demo, Inject observation, the scripted scenario progression — has been
> removed from both the UI and the API. It is kept for history only and
> cannot be followed against the current build.


## Thesis and wow moment

“A repair is not finished when a contractor leaves. RepairFlow keeps the original issue alive, understands what blocked it, and resumes work when the prerequisite is complete.”

The roof/scaffold case is the strongest primary demo because the audience can see a new dependency and a later causal resumption. It also exposes meaningful safety/approval boundaries. A simpler fallback is a plumber discovering a replacement part is needed, but do not change the implemented domain just to add a second story.

## Preparation

Confirm event rules and actual presentation duration. Prepare one synthetic property, tenant, fictional approved roofer and scaffolder; known non-emergency roof defect; dated tenant availability; deterministic mock slots and synthetic quoted amounts. The opening state contains no scaffold work order.

Check real Gemini schema/tool access, real ElevenLabs audio saving, webhook delivery and audio playback. Keep a previously captured live call as a clearly labelled replay contingency. Have no real contractor phone numbers enabled. Rehearse the complete loop, then reset only the synthetic case while retaining the integration evidence.

## Script — target 4:45

| Time | Presenter / participant | Visible application behavior |
|---|---|---|
| 0:00–0:20 | Explain the unresolved-case problem and the live/simulated boundary | One case workspace, no hidden scaffold branch |
| 0:20–1:15 | Start real browser voice. Tenant reports known roof ingress, confirms no immediate hazard and gives exact availability. Include an unscripted harmless detail | ElevenLabs conversation, in-call saved-case acknowledgment |
| 1:15–1:40 | End call; open transcript and briefly play actual audio | Spoken detail, conversation ID, structured availability and recorded audio. If still processing, show pending and return later |
| 1:40–2:00 | “The coordinator now plans the first visit.” | Live typed triage; mock appointment confirmed; visible tool/policy result |
| 2:00–2:40 | Inject SIMULATED contractor report: “The tiles are beyond safe ladder access. A scaffold platform is needed before I can repair them.” | Live Gemini interpretation; roofing BLOCKED; install prerequisite and removal follow-on appear; original issue remains open |
| 2:40–3:15 | Approve simulated scaffold scope/limit, inject installation/handover report and accept handover evidence | Accepted completion satisfies edge; original roofing order automatically resumes and gets a new mock appointment |
| 3:15–4:05 | Inject roof completion. Approve and finish required removal, then submit explicit tenant confirmation | Removal is released after roofing; all required work completes; case awaits/receives confirmation; RESOLVED |
| 4:05–4:30 | Show preserved first failed visit, source report and decision trail; optionally refresh after a pre-rehearsed restart | Same case/history/graph survives; no lost conversation |
| 4:30–4:45 | State architecture and limitation | One coordinator, typed proposals, deterministic policy, persistent jobs; real suppliers not integrated |

Do not make the judge wait for a second telephone call or a long search. If Tavily is enabled, show its logged query and candidate sources briefly while the first appointment is processing. Clarify that the booked demo supplier comes from the fictional approved network.

Scaffold installation, removal and handover each keep their required approval checks. Small explicit approval clicks are preferable to claiming the AI authorized hazardous work. The autonomous moment is the subsequent case continuation without a manager rebuilding the plan.

## Three-minute cut

Use a clearly labelled recording of the earlier real integration test for the opening 20 seconds, then demonstrate live report interpretation and dependency recovery. Show actual stored transcript/audio provenance. Cut search, detailed diagnostics and the restart demonstration. Retain approval, resumption and truthful final closure. Say which portions are replayed.

If removal has not completed, finish with “Leak repaired; removal remains outstanding” and an ACTIVE case. Do not force a green resolved badge for presentation convenience.

## Under-one-minute architecture explanation

“ElevenLabs captures the conversation, including the actual recording and transcript. Our Python backend stores the case and each observation. One Pydantic AI coordinator asks Gemini for a typed next action using current evidence. Ordinary code checks safety, authority, state and duplicate effects before executing it. Contractors are simulated in this demo; web search only proposes unverified candidates. Jobs and events live in the database, so a later report wakes a fresh decision. When scaffold completion satisfies the dependency, roofing becomes actionable again. The case closes only after required work and tenant confirmation.”

## Likely judge questions

| Question | Defensible answer |
|---|---|
| What is genuinely agentic? | Novel report interpretation changes the plan; fresh events cause bounded autonomous next-action selection |
| Is this just a scripted graph? | The initial graph lacks scaffolding; the model cites the new report to propose the edge. State guards and removal safety rule are deliberately deterministic |
| Why Pydantic AI? | Typed context/tools/output and bounded validation retries, central to the runtime |
| Why not multiple agents? | One operational responsibility and shared case state; extra handoffs add no demonstrated value |
| What persists? | Domain rows, event history, pending jobs/actions, transcript and actual audio metadata/file |
| How do you avoid double booking? | Unique action identity, persisted intent, connector acknowledgment, reconciliation for uncertain outcomes |
| Does Tavily know availability? | No; it returns source-linked claims. The mock approved network supplies simulated slots |
| Is anyone already doing this? | Yes, close products exist. This demo focuses on inspectable dependency recovery, not a first-to-market claim |
| What is real? | Gemini/Pydantic AI, live browser voice/recordings and optional Tavily; physical work and bookings are simulated |
| What about emergencies? | Immediate conservative escalation; no diagnosis or emergency dispatch claim |
| What about scale? | Local SQLite is deliberately bounded; always-on hosting/Postgres and stronger operations precede residents |
| What value is proven? | Published repair delays and coordination failure evidence; this product's savings and willingness to pay remain unmeasured |

## Sponsor visibility

Show the actual Gemini model ID and validated Pydantic AI run/tool output, with latency if measured. These are meaningful integrations. Mention Modal/Conduct only if asked; no verified prize rule justifies adding them. Rubric, special prizes and submission requirements remain unknown until organizers confirm them.
