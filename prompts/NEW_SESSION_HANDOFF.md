# Handoff to a new session

Paste this into a fresh chat in this repository. It carries what the
repository's own documentation cannot: the state of play as of
2026-09-21, the constraints still in force, and the traps that cost a
previous session real time.

---

## Who you are and what this is

You are continuing work on **RepairFlow** (the code and some docs call
it "Fixi"), a repair-coordination application for a small property
portfolio. It is **built and running** — do not rebuild it, and do not
believe any document that describes it as a specification awaiting
implementation. It began as a hackathon demo; that scope was retired on
2026-09-20 and the scripted demo layer was deleted.

**Read in this order before doing anything:**

1. `docs/APPLICATION_STATE.md` — the single current account of what
   exists, what works, what is broken, and what is undecided. §0 covers
   picking the project up on a new machine. It is kept reconciled
   against the code; trust it over the numbered specs.
2. `README.md` — what it is, and the exact bootstrap sequence.
3. `docs/26_SPECIFICATION_REVIEW.md` — the dated log of every deliberate
   deviation from the original specification. **Read the newest entries
   first.** They supersede the numbered specs wherever they conflict.
4. The canonical contracts, when you need one: `docs/06` (domain),
   `docs/07` (case state machine), `docs/10` (tool catalogue), `docs/16`
   (API), `docs/17` (database), `docs/19` (safety).

`docs/00`, `04`, `18`, `20`, `21`, `FIXI_UI_SPECIFICATION.md` and
`prompts/IMPLEMENTATION_PROMPT.md` describe the retired product or a
spent plan; each carries a banner saying so. `docs/audit/` holds twelve
read-only audits from 2026-09-20 — these are **historical inputs, not a
tracker**. Many findings in them were fixed afterwards.
`APPLICATION_STATE.md` is the tracker.

## Hard constraints — these are not negotiable and were not lifted

- **No outbound contact of any kind.** Do not place a call, send an SMS,
  an email, a real booking request or any other external message — not
  even once, not "just to check whether it works", not relying on an
  immediate hang-up or a later cancellation. `backend/app/integrations/
  no_contact.py` enforces this and arms itself automatically under
  pytest. Do not weaken it.
- **Never write to `backend/data/repairflow.db`.** It holds the only
  real call history that exists. Copy it to a temp path for any test,
  or point `DATABASE_PATH` at a scratch file.
- **Do not push, merge into `main`, or deploy.** There are 77 unpushed
  commits on `main` and that is intentional.
- **Do not modify the `liza.UI2` branch.**
- Live provider calls require an allowlisted recipient *and* a
  documented enable switch. Both are off.

## Getting it running

`backend/data/`, `backend/.venv/`, `node_modules/`, `frontend-fixi/dist/`
and `backend/.env` are all gitignored, so a clone has **no database, no
dependencies, no built frontend and no config**. README's *Running
locally, from a fresh clone* has the verified sequence. Two things that
will waste your time otherwise:

- **`uv` is a prerequisite nothing in the repo installs.** It provisions
  Python itself (3.12.13, pinned in `backend/.python-version`).
- **Build the frontend before starting the backend.** `main.py` mounts
  the SPA only `if FRONTEND_DIST.is_dir()`, checked once at import.
  Start first and `GET /` is a bare 404 for that whole process;
  building afterwards does not fix it. Restart uvicorn.

With no `.env`, operator auth is **on**: sign in as `operator` /
`repairflow-demo`. `GET /healthz` is the only unauthenticated route.
An empty database is a supported state — every screen has a real empty
state. `python -m app.seed` adds reference data; `python -m app.archive
--apply` adds 60 closed sample cases.

**The previous machine's data does not travel.** If you need those 14
cases and 3 `LIVE` communications, copy `backend/data/repairflow.db` by
hand.

## Traps that already cost someone a day

- **Verify by running, not by grepping.** Several defects here passed a
  careful read of the code and failed the moment something executed.
  Two examples: a Windows path separator made every unknown `/api/...`
  path return the SPA shell at **HTTP 200**, so a client would parse
  HTML as JSON and see success; and the test suite silently read the
  developer's untracked `.env`, so it went green every morning and red
  every afternoon on one machine only.
- **Every fix needs a test that fails when the fix is reverted.** Apply
  the mutation, watch the test fail, restore, watch it pass. A test that
  passes either way guards nothing — one written in this repo passed
  under mutation because the state it asserted had already been
  overwritten by the time it ran.
- **Tests must not read `backend/.env`.** `tests/conftest.py` disables
  `env_file` deliberately. Explicit `os.environ` still wins. Do not
  undo this.
- **Windows specifics.** Starlette hands `StaticFiles.get_response` a
  path already through `os.path.normpath`, which returns backslashes.
  `.gitattributes` pins the working tree to LF because `core.autocrlf`
  otherwise hands a Windows clone CRLF and `npx eslint .` then errors on
  every line of every file.
- **Bash heredocs in this harness eat backslashes**, even quoted ones.
  When a Python patch script needs a literal backslash, build it with
  `chr(92)` rather than writing `\\`.
- **One frontend.** `frontend-fixi/` is served. The old `frontend/`
  tree and the untracked `liza.UI2/` and `new UI/` design references were
  all deleted on 2026-09-21; the design refs live on the
  `origin/liza.UI2` branch and `frontend/` in history at `bd61137`.
- **`validateSearch` is avoided app-wide** in the frontend — it
  reproducibly froze the renderer against the SPA-fallback hydration
  shell. URL state uses `useRouterState` + `src/lib/search-params.ts`.
  Follow that; do not reintroduce `validateSearch`.
- **If you run subagents in parallel, partition them by directory.**
  Two agents editing overlapping files clobbered each other's work in a
  previous session, and a broad `git add -A` swept an agent's
  in-progress files into an unrelated commit. Do not `git add -A` while
  an agent is running.
- **Archive figures in the docs describe the dataset `--apply`
  generates, not the live database**, which currently holds zero
  archival rows.

## Where things stand

214 backend tests (`cd backend && uv run pytest -q`) and 62 frontend
tests (`cd frontend-fixi && npm test`). `tsc` clean, eslint 0 errors and
5 known warnings. The bootstrap was verified end-to-end from a checkout
containing only tracked files.

Six known problems remain open, all recorded with evidence in
`APPLICATION_STATE.md` §5, and three decisions need a human in §7. The
headline ones:

- **Row 1 — `MockBookingConnector` invents contractor availability**, a
  named CLAUDE.md prohibition and still the highest-severity item. It
  was *narrowed* on 2026-09-20 (bookings are no longer written
  `CONFIRMED`, and listing slots no longer persists rows through a
  model-visible read tool) but the times themselves are still
  fabricated. **A complete, file-by-file replacement plan is already
  written in §7.2 — read it before touching this.** Do not re-derive it.
- **Row 3 — no email or SMS transport.** Blocked by the no-contact
  constraint above, not by difficulty. Outward messages persist as
  drafts and say so.
- **Row 5 — enum CHECK constraints** protect only newly created tables.
  Retrofitting needs a table-rebuild migration against a database
  holding real data. This is the one genuinely risky item; treat it as a
  task of its own.
- **Row 10 — inconsistent error envelopes** across roughly 30 routes.
- **Rows 16 and 20** — no browser voice panel; a cosmetic React
  hydration mismatch on every page load.

`docs/UI2_TODO.md` item 3 (the Research drawer) is queued and blocked on
`CaseSnapshot` exposing the research id.

## How to work here

Follow `CLAUDE.md` — it is the project's standing instructions and is
loaded automatically. Beyond it: keep a runnable vertical slice, record
material corrections in `docs/26` **and** the affected canonical
contract before changing callers, and update `APPLICATION_STATE.md`
whenever you change what is true. Where a numbered spec and the running
code disagree, the code is usually right and the spec is usually stale —
but confirm which, and fix the loser rather than leaving the two
disagreeing.

Commit per logical fix with a message that explains *why*, not just
what. Do not push.
