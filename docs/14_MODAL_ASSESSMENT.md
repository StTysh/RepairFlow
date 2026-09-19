# 14 — Modal assessment

**Decision: optional, outside the one-day MVP.**

Modal supplies hosted Python execution, including CPU/GPU workloads, asynchronous spawned functions and scheduled functions. That is useful infrastructure, but this application mostly waits on HTTP providers and people. A normal asynchronous backend plus persistent jobs handles the demonstration. [Modal guide](https://modal.com/docs/guide).

| Potential responsibility | Benefit | Why it is not needed now |
|---|---|---|
| Background coordinator invocation | Independent scalable workers | One local worker already provides bounded runs and restart recovery |
| Parallel contractor research | Fan-out | A few I/O requests can use asyncio; API quotas remain |
| Scheduled follow-ups | Hosted schedules | Local due-job poller suffices while demo host is running |
| Large image/report processing | Isolated compute and optional GPU | No large-document or custom model workload in MVP |
| Batch evaluation | Run many independent scenario evaluations | Useful after the hero path, not needed to show it |

The concrete question is: **what can the normal backend not do during the hackathon?** For the selected scope, no compelling gap was found. Adding Modal now adds credentials, deployment, callbacks and reconciliation without improving the core story.

If time remains, a small optional Modal batch evaluates report paraphrases against the same typed coordinator and returns aggregate scores. This is honest supporting functionality, but should not replace the live dependency demo. Keep all case mutation in the backend; send only synthetic/de-identified inputs.

Modal's asynchronous invocation returns a call ID that can be used to retrieve results; documented result retention is not a substitute for permanent repair history. [Job queues](https://modal.com/docs/guide/job-queue). Scheduled functions are supported through Period/Cron mechanisms. [Scheduling](https://modal.com/docs/guide/cron).

Never share or copy the live SQLite file into cloud function workers. A future Modal worker would call the application's authenticated event API or use a properly shared database. It still needs idempotency and domain authorization.

The event names Modal as a technology partner and advertises unspecified provider credits. A Modal-specific prize, required usage or credit amount is **UNKNOWN / REQUIRES ORGANIZER CONFIRMATION**. Do not incur architectural complexity for an unverified award. [Event page](https://luma.com/ldn-hack).

Removing Modal from this design changes nothing in the core MVP; that is why it is excluded.
