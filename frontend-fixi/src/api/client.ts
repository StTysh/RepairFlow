// Operator credential storage + HTTP Basic auth attachment.
//
// Mirrors frontend/src/api/client.ts exactly (same sessionStorage key, same
// Basic-auth encoding, same /api/v1/readiness verification check) so both
// frontends stay interchangeable against the same RepairFlow backend and so
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

export const BASE_URL = import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:8000";

/** Verifies credentials against a cheap, always-available route. */
export async function verifyCredentials(creds: OperatorCredentials): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/api/v1/readiness`, {
    headers: { Authorization: authHeader(creds) },
  });
  return res.ok;
}
