# 12 — Build, Config & Deployment-Posture Security Audit

Scope: `backend/pyproject.toml`, `backend/uv.lock`, `frontend-fixi/package.json`,
`vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `scripts/flatten-dist.mjs`,
`backend/app/main.py`, `backend/app/config.py`, `backend/app/api/deps.py`,
`.gitignore`, `.gitattributes`, `backend/.env.example`. Read-only audit; nothing
in this tree was edited and the server was never started.

---

## Findings

### 1. CRITICAL — Real, live secrets and a real personal phone number are committed to the tracked repo

**File:** `docs/UI2_CHECKPOINT.md:70`

`backend/.env` itself was checked and confirmed **never committed** (`git log
--all --full-history -- backend/.env` returns nothing; only `backend/.env.example`
is tracked, and it ships with all secrets blank). That part of the design works.

However, `docs/UI2_CHECKPOINT.md` (tracked, present since commit `2adb8da` and
carried forward through `136dc0b`/`fe07a73`) contains this line verbatim:

```
- `backend/.env` has `OUTBOUND_CALLS_ENABLED=true` and
  `OUTBOUND_CALL_ALLOWLIST=["+44785XXXXXXX"]` (the user's real phone).
```

(Number redacted above; the original file has the full digit string.) That is
a real UK mobile number, explicitly annotated as "the user's real phone,"
committed in plain text to a markdown file that ships with the rest of the
repo (clone it, `grep` it, it's there). This is the exact PII/secret leakage
the audit brief asked to check for, and it is rated CRITICAL rather than HIGH
specifically because it is already permanent: it's sat in git history across
three commits, this is a local single-operator tool today but the repo can be
cloned, pushed, or shared at any point, and there is no way to un-leak it
short of history rewrite — unlike the other findings here, which are all
posture/config issues that stop being risks the moment the config changes.

I ran a full working-tree search (tracked and untracked/ignored alike) for
the number and the three real secret values above. Three hits, and only
three: `docs/UI2_CHECKPOINT.md` (this finding), `backend/data/repairflow.db`,
and this report's own first draft (now fixed — see the redaction note above).
`backend/data/repairflow.db` is expected: it's the live SQLite database, and
the number appears there because the app genuinely dialled it as part of
normal `PLACE_CALL`/Communication-ledger operation — that's the application
working as designed, not a leak, and `backend/data/` is correctly gitignored
(confirmed via `git ls-files`, nothing under it is tracked). No hits in
`node_modules`, `.venv`, recordings, or any `*.log` file (none exist outside
ignored directories). So the *only* place this needs cleaning up is the one
markdown file.

Separately, the live local `backend/.env` (uncommitted, correctly gitignored)
currently holds a **real Gemini API key, a real ElevenLabs API key, a real
ElevenLabs tool secret, a real ElevenLabs phone-number resource id**, and has
`OPERATOR_AUTH_ENABLED=false` **and** `OUTBOUND_CALLS_ENABLED=true` set
simultaneously, with the one real number above as the entire allowlist. That
combination is not committed, but it is the live state of the machine this
audit ran on — see Finding 2's "right now" note. Raw key/number values are
intentionally not reproduced in this report.

**Fix:** scrub the number out of `docs/UI2_CHECKPOINT.md` (replace with a
placeholder or a redaction note) and treat it as a credential exposure: since
it's been in git history across multiple commits, rewriting history or at
minimum rotating what can be rotated (the allowlist entry itself isn't
rotatable, but it should not be reused as a live test target once a redacted
doc ships) is warranted before this repo is shared externally.

---

### 2. HIGH — `OPERATOR_AUTH_ENABLED=false` removes all protection, and this machine currently has it off together with live outbound calling

**Files:** `backend/app/api/deps.py`, `backend/app/config.py`, every router in `backend/app/api/`

`require_operator` is applied as a router-level dependency
(`dependencies=[Depends(require_operator)]`) on every business router —
cases, observations, approvals, contractors, documents, notes, costs,
messaging, insights, reports, search, tenants, properties, overview, metrics,
and the `/api/v1/voice/*` operator surface. That's correctly comprehensive;
there's no route in `api/` that escapes it by omission. The two routers that
*are* unauthenticated on purpose — `webhook_router` (ElevenLabs post-call,
`/webhooks/elevenlabs`) and `tools_router` (`/integrations/elevenlabs/tools`)
— have their own independent checks: HMAC-SHA256 signature + timestamp-window
replay protection (`verify_webhook_signature`, constant-time compare) for the
webhook, and a `secrets.compare_digest`-checked bearer token for the tool
endpoints. Both are well-built; no finding there.

But `require_operator` itself has an explicit bypass:

```python
def require_operator(...) -> str:
    if not settings.operator_auth_enabled:
        return settings.operator_username
    ...
```

With `OPERATOR_AUTH_ENABLED=false`, **every one of those routes accepts every
request with no `Authorization` header at all** — full read on every case,
tenant, property, contractor, document, financial/cost record and message
thread, and full write access: create/edit cases, approve/reject
ActionProposals, upload/delete documents, compose messages, and start voice
sessions. There is no secondary gate (no IP allowlist, no separate flag) — the
single boolean is the entire perimeter.

This is documented as a "local dev convenience" default-off toggle, and
`backend/.env.example` correctly defaults it to `true`. But the **live
`backend/.env` on this machine has it set to `false`, at the same time as
`OUTBOUND_CALLS_ENABLED=true` with one real phone number in the allowlist**.
Today that's fine — uvicorn binds to `127.0.0.1` by default (README's run
command has no `--host`), so nothing off-box can reach it. The risk is
entirely latent until something changes the binding or exposes the port —
which the project's own architecture plans to do (CLAUDE.md: Quick Tunnels
for ElevenLabs webhook delivery). The moment a tunnel is up with this `.env`
unchanged, an unauthenticated party anywhere on the internet gets full
read/write on the case database and can drive the coordinator toward a
`PLACE_CALL` job against the one real number in the allowlist.

**Rate limiting / lockout / CSRF for Basic auth:** none exist, by design (this
is a single-operator local tool). `require_operator` does correctly use
`secrets.compare_digest` for both username and password (not `==`), which
protects against a timing side-channel, but there's no attempt- or
IP-throttling, so with auth *enabled*, the default credentials
(`operator` / `repairflow-demo`, shipped verbatim in `.env.example`) are
brute-forceable at whatever rate the network allows. Basic-auth credentials
are also "ambient" like cookies once a browser has them cached for an origin
— see Finding 3 for how that interacts with CORS.

**Fix:** before any exposure beyond `127.0.0.1` — including a Quick Tunnel for
webhook testing — flip `OPERATOR_AUTH_ENABLED` back to `true` and change the
password from the shipped default. This is already exactly what the code
comments say to do; it just isn't the state of the file that exists on disk
right now.

---

### 3. MEDIUM — CORS: default is safe, but nothing stops `allow_origins=["*"]` + credentials from being configured, and the effect would be a full credentialed-origin bypass

**Files:** `backend/app/config.py` (`cors_allow_origins`), `backend/app/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"],
    allow_headers=["*"],
)
```

`cors_allow_origins` is a plain `list[str]` read from `CORS_ALLOW_ORIGINS`
(JSON array) with no validator rejecting `"*"`. I checked the installed
Starlette 1.6.0 `CORSMiddleware` source directly
(`.venv/Lib/site-packages/starlette/middleware/cors.py`): it correctly
special-cases `allow_credentials=True` + `"*" in allow_origins` — it does
**not** emit a literal `Access-Control-Allow-Origin: *` in that case, it
reflects the requesting `Origin` back explicitly with `Vary: Origin`
(`send()`, lines 166–168). That's the "safe" Starlette behavior, but it means
a wildcard origin combined with credentials doesn't fail closed — it silently
becomes **allow literally any origin, with credentials, with any header**.
Combined with Basic auth being an ambient, browser-cached credential (browsers
attach it automatically to matching-origin requests without script access to
the password), a misconfigured `CORS_ALLOW_ORIGINS=["*"]` on a deployed
instance would let any website a logged-in operator visits make authenticated
reads/writes against this API from the victim's browser. The default
(`["http://localhost:5173"]`, and the live `.env`'s
`["http://localhost:5173", "http://localhost:5174"]`) is fine; this is purely
a config-time footgun with no guardrail.

`allow_methods` is explicit (not `["*"]`) and deliberately includes
DELETE/PATCH/PUT with a comment explaining why (ASGITransport tests don't
preflight, so a missing method here is invisible until exercised from a real
cross-origin browser). `allow_headers=["*"]` is broad but standard for a JSON
API and not independently dangerous given the origin restriction holds.

**Fix:** add a startup assertion/validator that rejects `"*"` in
`cors_allow_origins` when `allow_credentials=True` (or just refuse to boot),
so this class of misconfiguration is caught at config-load time rather than
relying on operators reading Starlette's source to understand the interaction.

---

### 4. LOW — `SpaStaticFiles` fallback is correctly scoped; one path (`/healthz`) sits outside its own exclusion list

**File:** `backend/app/main.py`

Path traversal: not exploitable. Starlette's own `StaticFiles.get_path` /
`lookup_path` (`.venv/Lib/site-packages/starlette/staticfiles.py`) normalizes
the path, rejects a leading `/` or `\`, and enforces
`os.path.commonpath([full_path, directory]) == directory` before ever
touching disk — this runs *underneath* `SpaStaticFiles.get_response`'s
override, so `..`-style traversal is blocked before the subclass logic sees
it, regardless of what `SpaStaticFiles` does.

The exclusion list (`api/`, `webhooks/`, `integrations/`, `assets/`) correctly
matches every actual route prefix in the app (`/api/v1*`,
`/webhooks/elevenlabs`, `/integrations/elevenlabs/tools`) plus the Vite build
output directory, so a genuinely missing endpoint under any of those prefixes
still 404s instead of silently returning the SPA shell — the failure mode the
audit brief was checking for does not occur for API traffic. The one gap:
`/healthz` is registered directly on `app`, outside `/api/v1`, and is *not* in
the exclusion list. A request to `/healthz` itself is matched by the explicit
route (registered before the mount) and works correctly, but any near-miss —
a typo, a monitoring probe hitting `/health` or `/healthz/` — falls through to
the SPA catch-all and gets **200 + HTML** instead of 404. For a liveness
probe that only checks status code, this would read as "healthy" when it
isn't actually checking anything. Low impact today (single `/healthz` call
site, presumably typed correctly), but worth closing.

**Fix:** add `"healthz"` (or move health under `/api/v1/healthz`) to the
exclusion tuple.

---

### 5. HIGH — Document preview: content-type is fully caller-controlled, enabling stored SVG content that executes script on direct navigation

**File:** `backend/app/api/documents.py`

```python
content_type=file.content_type or "application/octet-stream",
...
is_previewable = doc.content_type.startswith("image/") or doc.content_type in _INLINE_CONTENT_TYPES
disposition = "attachment" if (download or not is_previewable) else "inline"
```

`doc.content_type` is taken verbatim from the multipart part's client-supplied
`Content-Type` header — nothing validates it against the actual file bytes
(no magic-byte sniff, no Pillow `Image.open` check, no allowlist of real
image subtypes). A caller can upload a file whose bytes are an SVG containing
`<script>` while declaring `Content-Type: image/svg+xml`. `image/svg+xml`
matches `startswith("image/")`, so `get_document_content` serves it with
`Content-Disposition: inline` and `media_type: image/svg+xml`.

I checked how the frontend actually renders previews
(`frontend-fixi/src/components/fixi/DocumentsPanel.tsx`): the in-app preview
path is comparatively safe — it fetches the blob via authenticated `fetch()`
and renders it with `<img src={blobUrl}>` (`content_type.startsWith("image/")`
branch), and browsers disable script execution for SVGs loaded in image
context (`<img>`), including `blob:` URLs. The download path also forces
`a.download = ...`, which saves rather than navigates. So the app's own UI
does not trivially self-XSS.

The gap is the raw endpoint itself: `GET /api/v1/documents/{id}/content` is
reachable directly (Basic-auth only), and both an operator typing/pasting
that URL and, concretely, **right-clicking the rendered `<img>` preview and
choosing "Open image in new tab"** perform a top-level navigation to that
URL. A top-level navigation to an `image/svg+xml` response with
`Content-Disposition: inline` **does** execute embedded `<script>` in
Chrome/Firefox — unlike the `<img>` context. That's a same-origin stored XSS:
whoever opens that link runs script in the app's origin, with the browser's
cached Basic-auth credentials automatically attached to any subsequent
same-origin `fetch`/`XHR` the injected script issues, i.e. it can perform
authenticated writes as the victim operator without ever touching their
password.

**Attacker precondition:** this requires upload access, i.e. either a
currently-authenticated operator (who could be a legitimate-but-malicious
insider, or a second operator once this stops being single-operator) or, per
Finding 2, anyone at all when `OPERATOR_AUTH_ENABLED=false`. It is not
exploitable by an anonymous outsider against a properly-authenticated
instance without also compromising an operator session first — worth stating
plainly since it changes how urgent this is relative to Finding 1/2.

For completeness on the other two things the brief asked about here: the
generated `stored_name` (`uuid4().hex + _sanitized_suffix(...)`) is not
derived from the untrusted filename in any way that reaches the filesystem —
`_sanitized_suffix` only ever contributes a regex-validated
`[A-Za-z0-9]{1,10}` extension, so a traversal-shaped filename
(`../../etc/passwd`) cannot influence where bytes land; that part is solid.
`Content-Disposition`/filename header injection is covered separately below
(Finding 7).

**Fix:** don't trust `file.content_type` for the previewability/inline
decision. Either (a) restrict `_INLINE_CONTENT_TYPES`/the image-prefix check
to a fixed allowlist that excludes `image/svg+xml` (simplest — SVG is the
only common "image/*" type capable of carrying script), or (b) sniff the
actual bytes (e.g. `imghdr`/Pillow) and only trust that. Also worth adding
`Content-Security-Policy: script-src 'none'` (or at minimum
`X-Content-Type-Options: nosniff`) on the content-serving response as
defense in depth.

---

### 6. MEDIUM — Upload size cap is enforced after the body is already fully received, not before

**File:** `backend/app/api/documents.py` (`_read_capped`), confirmed against the installed Starlette

The code comment on `max_document_bytes` says the app-level read is chunked
specifically to avoid buffering an unbounded body in application code, and
`_read_capped` does genuinely stop accumulating once `max_bytes` is exceeded.
But that check runs on a `fastapi.UploadFile` that Starlette's own multipart
parser has **already fully received and written** by the time the route
handler starts — `file: UploadFile = File(...)` is resolved as a dependency
before the handler body runs, and that resolution parses the whole multipart
body. I confirmed this directly in the installed package
(`.venv/Lib/site-packages/starlette/formparsers.py:147-230`):
`MultiPartParser.spool_max_size = 1024 * 1024`, backing each file part with
`tempfile.SpooledTemporaryFile(max_size=1024*1024)` — up to 1MB held in
memory, everything beyond that spooled to disk, with **no upper bound**
imposed by the framework at that stage. So a caller can already push an
arbitrarily large body (multi-GB) through to a temp file on disk before
`_read_capped`'s 25MB check ever gets a chance to reject it. The temp file is
cleaned up when the request ends, so this isn't a permanent-storage-growth
bug, but it is a real transient disk/IO exhaustion vector if this endpoint is
reachable by more than the trusted local operator — not the "trivial memory
exhaustion" the comment guards against, but a real, larger disk-based one.

**Fix:** either configure Starlette's form parser with a smaller
`spool_max_size` and an actual max body size (Starlette's newer
`Request.form(max_files=..., max_fields=...)` doesn't cap bytes; a
`Content-Length`-based early rejection before parsing, or a custom ASGI
middleware capping request body size, is the correct fix) or accept this is
fine for a single-operator local tool and document it as a known limit rather
than an enforced one.

---

### 7. LOW/NIT — `Content-Disposition` filename sanitization is thin but the transport layer covers the gap

**File:** `backend/app/api/documents.py`

```python
safe_name = doc.display_name.replace('"', "")
headers = {"Content-Disposition": f'{disposition}; filename="{safe_name}"'}
```

Only `"` is stripped; embedded CRLF from an uploaded filename is not filtered
before being placed into the header value. I tested this concretely against
the actual installed stack rather than assuming: `starlette.responses.Response`
itself does **not** validate header values at construction (a CRLF-containing
value builds without error), but both of uvicorn's HTTP implementations do
reject it before it reaches the wire — `h11.Response(...)` raises
`LocalProtocolError: Illegal header value` for an embedded `\r\n`, and
uvicorn's `httptools` protocol (`protocols/http/httptools_impl.py:495-499`,
`HEADER_VALUE_RE`) independently raises `RuntimeError("Invalid HTTP header
value.")`. So a crafted filename with embedded CRLF currently degrades to a
500 on download/preview, not actual header/response splitting. Still worth
tightening `_sanitized_suffix`'s sibling logic to strip control characters
from `display_name` (or the `Content-Disposition` value) directly, so the
failure mode is a clean rejection at upload time instead of a 500 discovered
at download time, and so the safety doesn't rest entirely on the ASGI
server's behavior.

---

### 8. LOW — Dependencies

- **Backend (`uv.lock`):** fully pinned with hashes for every resolved
  package (`uv.lock` is a lockfile in the proper sense — exact versions +
  sdist/wheel hashes, not just range specifiers). Notable direct deps with
  upload/parsing surface: `python-multipart 0.0.32` (well past the
  `0.0.7` ReDoS fix, CVE-2024-24762 — not applicable), `httpx 0.28.1`,
  `aiosqlite 0.22.1`, `uvicorn[standard]>=0.53.0` (resolves to a version
  bundling `httptools`/`h11`/`websockets`, both checked above and behaving
  correctly on header validation). Nothing in the direct dependency list
  stood out as carrying a known unpatched CVE at the pinned versions.
- **Frontend:** `npm audit --omit=dev` against the committed
  `package-lock.json` (lockfileVersion 3) reports **0 vulnerabilities**. I
  did not install anything, per instructions.
- **Two lockfiles are committed** (`package-lock.json` *and* `bun.lock`,
  both tracked), implying both npm and bun are viable install paths. That's
  a hygiene/consistency risk (they can drift and silently resolve different
  transitive trees) rather than a security one; worth picking one.
- **`overrides.rolldown: "1.2.1"`** in `package.json`: Vite 8.x's dependency
  tree pulls in `rolldown` (Vite's Rust-based bundler, used here via
  `rolldown-vite`) as a transitive dependency of multiple packages, and this
  override forces all of them to resolve to one exact `rolldown` version
  instead of letting npm's resolver potentially install two divergent
  copies (which — per Vite's own guidance for this migration period — can
  produce plugin/version-mismatch build failures). It's a build-stability
  pin, not a security pin.

---

### 9. MEDIUM — `flatten-dist.mjs`'s `404.html` copy is load-bearing for the backend's SPA fallback, not redundant

**Files:** `frontend-fixi/scripts/flatten-dist.mjs`, `backend/app/main.py`, `.venv/Lib/site-packages/starlette/staticfiles.py`

Ran `rm -rf dist && npm run build` from a clean `frontend-fixi/` state: it
succeeds (client bundle, prerendered `index.html`, then the Nitro SSR bundle
that `flatten-dist.mjs` deletes). The script's Windows-specific handling is
real and necessary: POSIX `rename()` silently overwrites an existing
directory at the destination, but Windows `renameSync` throws `EPERM` if the
destination already exists — the script's `rmSync` of any stale `dest`
before each `renameSync` is exactly the right fix for repeated/incremental
builds on this OS. It also removes `dist/server/` and copies `index.html` →
`404.html` after flattening.

The script's own comment says that `404.html` copy exists because "FastAPI's
current mount... does NOT catch-all unmatched paths," and adds: "If a future
phase changes the mount to a real catch-all route, this file becomes
redundant but harmless." That future phase already happened —
`SpaStaticFiles` in `main.py` is exactly that catch-all — so I initially read
this as confirming the comment's own prediction (redundant, safe to drop).
Tracing the actual control flow says the opposite: it's still required, and
removing it would silently break every deep link.

`SpaStaticFiles.get_response` is:

```python
async def get_response(self, path: str, scope):
    response = await super().get_response(path, scope)
    if response.status_code == 404 and not path.startswith(("api/", ...)):
        return await super().get_response("index.html", scope)
    return response
```

The catch depends on `super().get_response(...)` *returning* a 404 rather
than *raising* one. Starlette's base implementation
(`staticfiles.py:147-152`) does both, conditionally:

```python
if self.html:
    full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, "404.html")
    if stat_result and stat.S_ISREG(stat_result.st_mode):
        return FileResponse(full_path, stat_result=stat_result, status_code=404)
raise HTTPException(status_code=404)
```

If `404.html` exists in the served directory, a miss comes back as a
`FileResponse(..., status_code=404)` — an ordinary return value, which is
exactly what `SpaStaticFiles.get_response` inspects and rewrites to serve
`index.html` instead. If `404.html` does **not** exist, the base class
instead `raise`s `HTTPException(status_code=404)` directly out of that
`await super().get_response(path, scope)` call — and `SpaStaticFiles`
wraps that call in no `try`/`except`, so the exception propagates straight
past the `if response.status_code == 404` check (which never runs) and out
to FastAPI's default exception handling, which just returns a real 404.

So the SPA-fallback behavior this class's own docstring describes — "a
`/properties/<uuid>` reload should serve the app shell, not 404" — currently
works **only because** `flatten-dist.mjs` happens to also produce
`dist/404.html`. The two files implement one feature jointly, but nothing
declares that dependency: `SpaStaticFiles`'s docstring reads as if it's
self-sufficient, and the build script's own comment actively suggests the
404.html step is now safe to delete. If anyone acts on that comment (e.g.
while cleaning up the "future phase" that already arrived), every
non-root deep link and every page reload silently reverts to a real 404 —
exactly the regression the class was written to prevent — with no test
currently wired to catch it (this audit didn't find a test hitting an
unmatched SPA path against a built `dist/`).

**Fix:** delete or rewrite the stale comment in `flatten-dist.mjs` to state
the actual (inverted) dependency — the `404.html` copy is required by
`SpaStaticFiles`, not superseded by it — and consider a small backend test
that builds/fakes a `dist/` with and without `404.html` and asserts the
fallback behavior, so this coupling is enforced rather than just documented.

`frontend-fixi/dist` is gitignored via its own local `frontend-fixi/.gitignore`
(`dist`), confirmed with `git check-ignore -v`. Nothing in the backend or the
build scripts reads from a committed `dist/` — `main.py` mounts it
conditionally (`if FRONTEND_DIST.is_dir()`), so a fresh clone without a build
step simply serves no frontend, which is correct, discoverable behavior
rather than a silent failure.

Grepped the built `dist/` bundle for API-key-shaped strings, bearer tokens,
and the operator default password — none found. The frontend build carries
no server secrets, consistent with `config.py`'s docstring ("All secrets are
read server-side only") and the fact that none of the `*_API_KEY` values are
referenced anywhere under `frontend-fixi/src`.

---

### 10. LOW — Repo hygiene

- **`.gitattributes`:** only exists at `frontend-fixi/.gitattributes`
  (`* text=lf`), with a clear comment explaining why (Windows
  `core.autocrlf=true` would otherwise rewrite every file to CRLF on
  checkout and fail `prettier`'s LF-default rule on a fresh clone). There is
  **no root-level or `backend/`-level `.gitattributes`**. I checked whether
  this produces any actual line-ending noise right now: `core.autocrlf` on
  this machine is `true`, and a spot-check of `backend/app/main.py` /
  `config.py` shows CRLF on disk (per `file`) while `git diff`/`git status`
  currently show **no line-ending-driven modifications** — this working tree
  had unrelated, genuine in-progress edits at the time of this audit (other
  work happening on the same checkout during a live session), and the
  modified backend files I inspected had real logic diffs, not whitespace
  churn, so the missing
  `.gitattributes` for `backend/` is not currently causing any phantom
  diffs. It is nonetheless a latent inconsistency: `backend/`'s line-ending
  behavior depends entirely on each contributor's local `core.autocrlf`
  setting rather than being pinned by the repo, so a contributor with
  `core.autocrlf=input` or `=false` could commit CRLF into a backend file
  without anything catching it.
- **No committed artefacts that shouldn't be there.** Checked explicitly via
  `git ls-files`: no `backend/data/*`, no `*.db`, no `frontend-fixi/dist/*`,
  no `node_modules/`, no `.venv/`. `backend/data/` is covered by both the
  generic `data/` and the explicit `backend/data/` line in the root
  `.gitignore`. The only "real" leak found is the phone number in Finding 1
  — everything else expected to be ignored, is.

---

## "If you deployed this tomorrow" — in order

1. **Set `OPERATOR_AUTH_ENABLED=true` and change `OPERATOR_PASSWORD` off the
   shipped default** before the process is reachable from anything but
   `127.0.0.1` — this includes standing up the Quick Tunnel the project's own
   architecture calls for. The live `.env` on this machine currently has auth
   **off** at the same time outbound calling is **on** with a real number
   configured; that specific combination should not go anywhere near a
   tunnel unmodified.
2. **Redact the phone number in `docs/UI2_CHECKPOINT.md`** and treat it as an
   already-leaked credential/PII — it's been in git history across three
   commits.
3. **Fix the SVG content-type trust issue in `documents.py`** (Finding 5)
   before documents can be uploaded/shared by anyone other than the single
   trusted operator — this is the one finding here that's a real stored-XSS
   primitive, not just a misconfiguration risk.
4. Add the CORS wildcard+credentials guardrail (Finding 3) and a real
   upload size limit enforced before the body is fully spooled (Finding 6)
   before opening the API beyond localhost.
5. Not a blocker, but fix before it bites someone: don't let
   `flatten-dist.mjs`'s `index.html` → `404.html` copy get "cleaned up"
   (Finding 9) — deleting it, following the script's own stale comment,
   would silently turn every deep-linked page reload into a real 404 the
   next time someone touches that file.

## Severity counts

CRITICAL: 1 · HIGH: 2 · MEDIUM: 3 · LOW: 4
