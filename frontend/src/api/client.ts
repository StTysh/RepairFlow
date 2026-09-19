import createClient from "openapi-fetch";
import type { paths } from "./schema";

const AUTH_STORAGE_KEY = "repairflow.operator.auth";

export interface OperatorCredentials {
  username: string;
  password: string;
}

export function loadStoredCredentials(): OperatorCredentials | null {
  const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OperatorCredentials;
  } catch {
    return null;
  }
}

export function storeCredentials(creds: OperatorCredentials) {
  sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(creds));
}

export function clearCredentials() {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
}

function authHeader(creds: OperatorCredentials): string {
  // btoa is fine here: this runs only in the browser, over a value the
  // operator just typed into a same-origin login form, not a secret we
  // fetched from anywhere -- it's the standard HTTP Basic encoding, not
  // an attempt at confidentiality.
  return `Basic ${btoa(`${creds.username}:${creds.password}`)}`;
}

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function createApiClient(creds: OperatorCredentials) {
  const client = createClient<paths>({ baseUrl: BASE_URL });
  client.use({
    onRequest({ request }) {
      request.headers.set("Authorization", authHeader(creds));
      return request;
    },
  });
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Verifies credentials against a cheap, always-available route. */
export async function verifyCredentials(creds: OperatorCredentials): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/api/v1/readiness`, {
    headers: { Authorization: authHeader(creds) },
  });
  return res.ok;
}

/**
 * GET /cases/{id} returns 304 with no body when known_version matches the
 * server's current version -- openapi-fetch's client.GET would try to parse
 * that as JSON and throw, so this bypasses it and handles 304 explicitly.
 */
export async function fetchCaseDetail(
  creds: OperatorCredentials,
  caseId: string,
  knownVersion?: number,
): Promise<{ status: 304 } | { status: 200; body: paths["/api/v1/cases/{case_id}"]["get"]["responses"][200]["content"]["application/json"] }> {
  const url = new URL(`${BASE_URL}/api/v1/cases/${caseId}`);
  if (knownVersion !== undefined) url.searchParams.set("known_version", String(knownVersion));
  const res = await fetch(url, { headers: { Authorization: authHeader(creds) } });
  if (res.status === 304) return { status: 304 };
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
  return { status: 200, body: await res.json() };
}
