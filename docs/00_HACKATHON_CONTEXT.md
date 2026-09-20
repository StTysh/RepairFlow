# 00 — Hackathon context and rule uncertainty

> **Superseded (2026-09-20).** This researches the rules and provider
> entitlements of a hackathon that ended on 19 September 2026. The event
> is over, the demo it was researched for was delivered, and the project
> has since been migrated into a general application; none of the
> organizer-confirmation questions or eligibility uncertainty below are
> still live concerns. Read `docs/APPLICATION_STATE.md` for what the
> application actually is now. This file is kept as a record of the
> pre-event research.

Research date: 19 September 2026. Event date/location in the brief: London, 19 September 2026.

## Verified public facts

The [official Luma page](https://luma.com/ldn-hack) describes morning team formation, building during the day and evening demonstrations. It lists:

| London local time | Activity |
|---|---|
| 09:30 | Doors/networking |
| 10:00 | Opening/matchmaking |
| 12:30 | Lunch |
| 19:00 | Competition opt-in deadline/pizza |
| 20:00 | Live demos |
| 20:45 | Awards |

Capacity is 70; entry is first come, first served, even with a ticket. The exact address requires registration.

Google DeepMind and Conduct are co-hosts; Modal and Pydantic are technology partners. The page promises provider credits without amounts, redemption instructions or product allocation.

The extracted public page says Saturday but does not expose the full calendar date/timezone. The supplied date is retained; London local time is a planning assumption.

## Requirement classification

| Question | Evidence status |
|---|---|
| Objective | Working AI solution demonstrated within the day; agentic theme |
| Competition | Opt-in and live demos explicitly listed |
| Submission link, repo/video/deck requirements | UNKNOWN |
| Demo duration, judging rubric/weights | UNKNOWN |
| Team minimum/maximum, solo eligibility | UNKNOWN |
| Entirely event-created code; prior research/templates | REQUIRES ORGANIZER CONFIRMATION |
| Mandatory sponsor SDK/model | None stated; not proof that none exist |
| Sponsor challenges or special prizes | UNKNOWN |
| Sponsor usage affects prize eligibility | UNKNOWN |
| Prize amounts | UNKNOWN |

These findings describe what is published, not permission to ignore on-site rules.

## What each organisation actually provides

| Organisation | Publicly supported event role | Unverified benefit | Architectural consequence |
|---|---|---|---|
| Google DeepMind | Co-host/frontier-model partner | Specific Gemini model, quota, credit amount, mentoring allocation | Test the event key; do not assume every listed API model is enabled |
| Pydantic | Technology partner | Whether credits mean Logfire, Gateway, support or something else | Use open-source Pydantic AI meaningfully; Logfire optional |
| Modal | Technology partner | Amount, expiry, GPU allowance, special prize | No infrastructure dependence in core demo |
| Conduct | Co-host/enterprise-software product | Public hackathon API, credits or challenge | No invented integration |
| ElevenLabs/Tavily | Requested by project owner | Event sponsorship/credits not listed | Bring own access or use labelled fallback |

Provider-product assessments are in docs/09 and docs/13–15. Public technical capabilities do not establish attendee entitlements.

## Organizer questions at check-in

1. Are pre-event research, documentation, boilerplate and AI-generated code allowed?
2. What are team limits, opt-in mechanism, deliverables and exact demo time?
3. Which rubric and prize categories apply? Is sponsor usage required for any?
4. Which model endpoints and credit products are supplied, with what expiry?
5. Can demo integrations be simulated if explicitly disclosed?
6. Are public repositories, licences or IP terms required?

Record answers with speaker, time and source in docs/23. Do not contact organizers on the user's behalf without authorization. No organizer communication was sent in this research phase.

## Strategy under uncertainty

Target a four-minute demo with a three-minute cut. Build original implementation during the permitted window. Preserve this specification as pre-event preparation and disclose it if asked. Do not claim rule compliance until confirmed.

Show Gemini interpreting a novel report and Pydantic AI validating a typed action. Include a visible external tool call and persisted resumption. Add sponsor technology only when it improves that demonstration or a confirmed prize rule justifies the cost.

The schedule permits roughly nine hours from opening to opt-in, but lunch, setup and rehearsal reduce engineering time. The build plan budgets 7 hours 35 minutes of engineering plus contingency.
