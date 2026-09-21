import type { OperatorCredentials } from "@/api/client";

// Operator sign-in was removed on 2026-09-21 by owner decision: this build
// is a localhost prototype and the login step bought nothing but a way to
// lock yourself out.
//
// It also actively broke the app. `require_operator` answered an
// unauthenticated API call with `401 WWW-Authenticate: Basic`, which makes
// Chrome swallow the response to raise its own native credentials dialog --
// so LoginGate's "does this backend even need a login?" probe never
// settled, `checking` never cleared, and a fresh clone (auth defaults ON,
// per the README) rendered a permanently blank page and never reached the
// app's own sign-in form. See docs/26, 2026-09-21.
//
// The backend now defaults `operator_auth_enabled=False` and no longer
// sends a browser-triggering challenge. Every hook still asks for the
// operator identity through `useAuthedCreds()` -- it is what writes are
// attributed to -- so that call site is kept and answers with a fixed
// identity instead of a signed-in session. `api/client.ts` still attaches
// the header; with auth disabled the backend ignores it.
//
// To reintroduce real auth, this is the single seam: make this hook read a
// session again. Do NOT restore the `WWW-Authenticate: Basic` header
// without also handling the browser-dialog problem above.

const OPERATOR: OperatorCredentials = { username: "operator", password: "" };

export function useAuthedCreds(): OperatorCredentials {
  return OPERATOR;
}
