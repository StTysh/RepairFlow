// Operator credential storage + HTTP Basic auth attachment.
//
// Mirrors frontend/src/api/client.ts exactly (same sessionStorage key, same
// Basic-auth encoding, same /api/v1/readiness verification check) so both
// frontends stay interchangeable against the same Fixi backend and so
// this can be swapped in wholesale once real data wiring lands here.
//
// This file intentionally does NOT include frontend's typed openapi-fetch
// client yet -- that arrives with the data-wiring phase, once this app talks
// to the backend for more than login verification. Everything below this
// point is what that phase needs: storage, the auth header builder, and
// verifyCredentials to build a typed client on top of.

const AUTH_STORAGE_KEY = "repairflow.operator.auth";

export interface OperatorCredentials {
  username: string;
  password: string;
}

// SPA mode still runs one server-side render pass at build time to produce
// the prerendered shell (see vite.config.ts) -- sessionStorage doesn't exist
// in that Node environment, so every accessor below has to tolerate running
// without it.
function hasSessionStorage(): boolean {
  return typeof sessionStorage !== "undefined";
}

export function loadStoredCredentials(): OperatorCredentials | null {
  if (!hasSessionStorage()) return null;
  const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OperatorCredentials;
  } catch {
    return null;
  }
}

export function storeCredentials(creds: OperatorCredentials) {
  if (!hasSessionStorage()) return;
  sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(creds));
}

export function clearCredentials() {
  if (!hasSessionStorage()) return;
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
}

export function authHeader(creds: OperatorCredentials): string {
  // btoa is fine here: this runs only in the browser, over a value the
  // operator just typed into a same-origin login form, not a secret we
  // fetched from anywhere -- it's the standard HTTP Basic encoding, not
  // an attempt at confidentiality.
  return `Basic ${btoa(`${creds.username}:${creds.password}`)}`;
}

/** Where the API lives, relative to wherever this bundle is running.
 *
 * Three cases, in order:
 *
 *  1. `VITE_API_BASE_URL` set at build time -- always wins.
 *  2. The production build served by FastAPI itself (any port). The API is
 *     same-origin, so an empty base is correct and, importantly, portable:
 *     hardcoding `http://localhost:8000` here meant a build served on any
 *     other port silently called a *different* backend, which is exactly
 *     how a page can show a login form while its own server has auth
 *     disabled.
 *  3. `vite dev` on 5173/5174 -- the API is a separate origin, so point at
 *     the conventional backend port and let CORS handle it.
 */
const VITE_DEV_PORTS = new Set(["5173", "5174", "5175"]);

function resolveBaseUrl(): string {
  const configured = import.meta.env["VITE_API_BASE_URL"];
  if (configured) return configured;
  // The prerender pass runs in Node with no window; nothing fetches there,
  // but the module still evaluates, so this must not throw.
  if (typeof window === "undefined") return "http://localhost:8000";
  return VITE_DEV_PORTS.has(window.location.port) ? "http://localhost:8000" : "";
}

export const BASE_URL = resolveBaseUrl();

/** Verifies credentials against a cheap, always-available route. */
export async function verifyCredentials(creds: OperatorCredentials): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/api/v1/readiness`, {
    headers: { Authorization: authHeader(creds) },
  });
  return res.ok;
}

/** Thrown by `request()`/`requestOrNotModified()` below on a non-2xx
 * response, carrying the HTTP status so callers (mutations especially --
 * e.g. a stale case version) can branch on it instead of string-matching
 * the message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Turn an error response into a sentence a human can read.
 *
 * The API speaks three shapes and this used to understand only one:
 *
 *   {"error":{"code","message","retryable","correlation_id"}}  DomainError
 *   {"detail":[{loc,msg,type},...]}                            FastAPI validation
 *   {"detail":"..."}                                           raw HTTPException
 *
 * Only `detail` was unwrapped, so every DomainError -- the common case, and
 * the one behind every stale-version conflict and policy rejection -- fell
 * through to `JSON.stringify(body)` and reached the operator as a raw blob
 * in a toast: `Could not resume case: {"error":{"code":"STALE_VERSION",...`.
 * Fixed here rather than in each of the six mutation hooks that hit it, so
 * a shape the API already sends can never surface unparsed again.
 */
async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (!body || typeof body !== "object") return res.statusText;

    // DomainError envelope.
    const envelope = (body as { error?: unknown }).error;
    if (envelope && typeof envelope === "object") {
      const message = (envelope as { message?: unknown }).message;
      if (typeof message === "string" && message) return message;
    }

    if ("detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      // FastAPI validation: [{loc:["body","field"], msg:"Field required"}, ...]
      if (Array.isArray(detail)) {
        const parts = detail
          .map((d) => {
            if (!d || typeof d !== "object") return null;
            const msg = (d as { msg?: unknown }).msg;
            if (typeof msg !== "string") return null;
            const loc = (d as { loc?: unknown }).loc;
            const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
            return typeof field === "string" && field !== "body" ? `${field}: ${msg}` : msg;
          })
          .filter((p): p is string => Boolean(p));
        if (parts.length) return parts.join("; ");
      }
      if (detail !== undefined) return JSON.stringify(detail);
    }
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

/** Generic authenticated JSON request against the Fixi API. Every
 * data-fetching hook/endpoint function in src/api and src/hooks goes
 * through this (or requestOrNotModified below) so auth attachment and
 * error shape stay in one place. */
export async function request<T>(
  creds: OperatorCredentials,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: authHeader(creds),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }
  // 202 here still carries a JSON body (CaseVersionResponse etc. -- the
  // 202 just signals "accepted, coordinator will follow up asynchronously"
  // per docs, not "no content"). Only 204 has no body to parse.
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

/** GET that understands the API's `known_version` / 304-no-body polling
 * convention (see docs: case snapshot polling). openapi-fetch/plain fetch
 * both try to JSON-parse every response, which throws on a 304's empty
 * body -- this bypasses that by handling 304 explicitly, same as
 * frontend/src/api/client.ts's fetchCaseDetail. */
export async function requestOrNotModified<T>(
  creds: OperatorCredentials,
  path: string,
  knownVersion: number | undefined,
): Promise<{ status: 304 } | { status: 200; body: T }> {
  // `new URL` needs an absolute input, and BASE_URL is empty when the API
  // is same-origin -- so supply the current origin as the base rather than
  // throwing on a relative path.
  const url = new URL(
    `${BASE_URL}${path}`,
    typeof window === "undefined" ? "http://localhost:8000" : window.location.origin,
  );
  if (knownVersion !== undefined) url.searchParams.set("known_version", String(knownVersion));
  const res = await fetch(url, { headers: { Authorization: authHeader(creds) } });
  if (res.status === 304) return { status: 304 };
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res));
  return { status: 200, body: (await res.json()) as T };
}
