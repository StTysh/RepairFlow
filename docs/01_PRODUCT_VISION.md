# 01 — Product vision and validation

## Product

**RepairFlow is a supervised autonomous coordinator for maintenance cases that need more than one visit or trade.** It owns progression between interactions: what remains unresolved, what blocks progress, who needs to respond and when to follow up.

This is a bounded operational agent. It can choose the next permitted step and interpret unexpected outcomes. It cannot authorize unsafe work, certify a property safe or invent supplier capacity.

## Buyer and user

Initial buyer hypothesis: head of property management at an English residential letting agency with a preferred-contractor network and enough managed homes to have dedicated maintenance coordination. Portfolio size of 300–3,000 homes is an **ASSUMPTION for discovery**, not a validated market boundary.

Daily user: property manager supervising approvals, ambiguous evidence and overdue responses. Other participants: tenant, contractor, landlord budget owner and, later, housing repairs/compliance teams.

Housing associations offer compelling evidence and larger case volume, but procurement, safety obligations, accessibility and housing-management-system integration make them a later pilot segment.

## Current gap we can demonstrate

The broad idea already exists in commercial products. [askporter](https://www.askporter.com/housing/repair-journey) advertises progression through reporting, scheduling, access and feedback; [AppFolio](https://www.appfolio.com/property-manager/maintenance) markets an AI maintenance coordinator.

Our defensible hackathon claim is narrower: **watch a free-text site report become an explicit dependency, then see the original repair resume after verified prerequisite completion.** We have not established that competitors cannot do this.

The provisional wedge is transparent exception handling: evidence-linked decisions, dependency state, controlled commitments, restart recovery and resident-verified closure. Commercial defensibility would require integration quality, operational data and measured results, not the presence of an LLM.

## Success and failure

Success: a safe, scoped case progresses without a manager repeatedly reading history and chasing the next person. The system shows what it knows, what it is waiting for and what it has actually done.

Failure: a convincing voice agent creates another ticket that someone must manually coordinate; a visit is mistaken for resolution; the same job is booked twice; a hazard waits in an ordinary scheduling queue.

## Product principles

1. Preserve the underlying issue across failed visits and follow-on work.
2. Treat external statements as observations, with attribution and time.
3. Choose a next action from current state; do not replay old instructions.
4. Let code own authority, transitions, money limits and transaction integrity.
5. Make waiting an explicit durable state with an owner and follow-up deadline.
6. Show the difference between a proposal, an approval, an attempted action and a confirmed result.
7. Require affirmative evidence before resolution.
8. Keep prototype simulations unmistakable.

## Research verdict

| Hypothesis | Verdict |
|---|---|
| Coordination failures exist | Supported; see docs/02 |
| Agencies pay to manage maintenance | Established category; willingness to pay for this product unvalidated |
| Voice intake is novel | Rejected |
| Autonomous follow-through is unique | Rejected as a broad claim |
| Dynamic dependency recovery is a strong demo | Yes; specific and observable |
| One agent is sufficient | Yes for this bounded domain; see docs/08 |
| Full original scope fits one day | No; cut telephony, real procurement and general workflow configuration |

## Discovery after the event

Interview five property managers and two contractors. Ask them to reconstruct recent multi-visit cases from actual records: handoffs, follow-up gaps, minutes spent, missed access, permissions and reasons for delay. Ask where their existing system already automates this.

A pilot should initially propose actions in shadow mode. Compare coordinator minutes, unresolved case age, missed access, duplicate contacts and inappropriate closure against a comparable baseline. A time saving is not a tenant-outcome improvement unless both are measured.
