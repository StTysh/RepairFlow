# 18 — Case workspace and visible agency

## Stack

React + TypeScript + Vite; Tailwind/shadcn components; React Flow for the small work graph. FastAPI serves the production build. No Next.js server is needed for this authenticated operational demo. [Vite](https://vite.dev/guide/), [shadcn](https://ui.shadcn.com/docs), [React Flow](https://reactflow.dev/learn).

React Flow provides nodes/edges and viewport interaction; it does not own domain transitions. The graph is rendered from WorkOrder/Dependency records, with stable IDs and deterministic positions. Three work nodes do not need an automatic layout engine.

## Primary screen

A judge opens one active case directly. Use a compact top summary, a large central dependency graph, a next-action/approval panel and a timestamped timeline. A small side rail contains tenant/property, availability and evidence. A generic table may navigate cases but must not dominate the hero view.

| Region | Required content |
|---|---|
| Case header | Original issue, location, urgency, case status, current blocker and last updated time |
| Work graph | Roofing/install/removal nodes; status text/icons; prerequisites; active appointment attempt |
| Next action | Short evidence-linked explanation, proposed action, approval/wait/error state |
| Activity timeline | Caller report, model decision, policy result, connector acknowledgment, report, block/unblock |
| Communication drawer | Actual speaker-labelled transcript, audio player, conversation ID, structured outcome and recording status |
| Research drawer | Actual Tavily query/time/request ID/sources; unverified candidates separate from approved suppliers |
| Demo controls | Explicitly labelled simulated observations; never concealed behind real provider branding |

## Hero graph behavior

Initially show a roofing order only. When the report arrives, keep the roofing node visible and change it to BLOCKED. Add scaffold installation as its prerequisite and removal as the roof's dependent follow-on. Emphasize the new edge and the cited report. Do not animate success before the transaction commits.

After accepted handover, mark the prerequisite edge satisfied and roofing READY, then SCHEDULED only when mock booking confirms. Preserve the failed first appointment in its expandable history. After roofing completion, removal becomes actionable. Final case closure appears only after removal and tenant confirmation.

Colors supplement text: blocked, awaiting approval, ready, scheduled, completed, escalated. Include accessible labels/icons and do not rely on green/red alone. Keep the original issue visible throughout; a completed contractor visit must not visually imply the issue is fixed.

## Reasoning and tools

Show “Report says roof access requires scaffold; roofing remains unresolved” with a report link. Do not show private chain of thought or a fabricated thinking animation. Show real orchestration-run timestamps, model ID, tool names and policy result. If a model is still running, say so; if timeout, show retry/review state.

Show distinct provenance badges per event/effect: LIVE, SIMULATED, FIXTURE. A case can mix live voice, live Gemini and simulated booking. One global “Live” badge would be misleading.

## Voice evidence states

Before call: disclosure and permission to use microphone. During call: connected/listening/speaking indicators from the provider SDK, plus saved-case acknowledgment. After call: “Transcript processing” and “Recording pending” until evidence arrives.

The audio player is enabled only when the backend has saved nonempty bytes. Missing recording shows failure reason and retry; a transcript never masquerades as audio evidence. Highlight the actual caller phrase used in the live acceptance test and its resulting availability/next action.

## Interaction and transport

Use versioned HTTP polling every second during active work, five seconds while idle; events fetch after the last seen sequence. Include version and latest_event_seq so recording-only updates render. Polling avoids the selected development tunnel's SSE restriction documented in 05.

Approval panel shows exact scope, simulated/real status, amount when known, evidence and reason. Approving sends proposal hash/version; stale approval prompts a refresh. No dropdown directly changes case/work status.

Keep the app operable at laptop presentation resolution and keyboard accessible. Use a fixed initial graph viewport and large readable labels. Prefer a clear timeline and three-node graph over adding maps, generic chat, charts or decorative agent avatars.

## Screens outside MVP

Supplier onboarding, portfolio analytics, tenant portals, mobile field apps, invoice/payment screens and production account management are excluded. A simple diagnostics drawer is for operators, not part of the tenant conversation.
