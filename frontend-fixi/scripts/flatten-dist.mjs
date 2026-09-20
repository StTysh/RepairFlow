// TanStack Start's SPA-mode build (see vite.config.ts) writes a client bundle
// to dist/client/ and a transient Nitro server bundle to dist/server/ -- the
// server bundle exists only so the build can prerender the SPA shell; nothing
// runs it afterwards. This script drops dist/server/ and flattens
// dist/client/* up to dist/ so the published output matches frontend/dist's
// shape (a single directory with index.html + assets/ at the top level),
// which is what FastAPI's StaticFiles mount expects.
import { copyFileSync, existsSync, readdirSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";

const distDir = join(import.meta.dirname, "..", "dist");
const clientDir = join(distDir, "client");
const serverDir = join(distDir, "server");

if (existsSync(serverDir)) {
  rmSync(serverDir, { recursive: true, force: true });
}

if (existsSync(clientDir)) {
  for (const entry of readdirSync(clientDir)) {
    const dest = join(distDir, entry);
    // Windows rename() refuses to overwrite an existing directory (unlike
    // POSIX rename), so a stale flattened output from a previous build
    // makes this EPERM on every rebuild unless cleared first.
    if (existsSync(dest)) {
      rmSync(dest, { recursive: true, force: true });
    }
    renameSync(join(clientDir, entry), dest);
  }
  rmSync(clientDir, { recursive: true, force: true });
}

// This app has client-side routes beyond "/" (/maintenance,
// /maintenance/tickets/$id/{-$section}, /properties/...), so deep-linking
// or refreshing any of them has to reach the SPA shell. That is now the
// backend's job: SpaStaticFiles in backend/app/main.py is a real
// catch-all, falling back to index.html for any unmatched path that is
// not under /api, /webhooks, /integrations or /assets.
//
// This copy is therefore genuinely redundant *for the FastAPI mount* --
// but it is not dead, and it is not only a comment away from being
// deleted. It is what makes the same dist/ directory work unchanged on a
// static host (GitHub Pages, Netlify, `npx serve`), none of which run the
// backend. It also costs one 3 KB file. Keep it.
//
// It used to be load-bearing in a way nothing recorded: Starlette's
// html=True mode *returns* 404.html on a miss when the file exists and
// *raises* HTTPException(404) when it does not, and main.py only handled
// the returned form. Deleting this copy would have 404'd every deep link.
// main.py now handles both, and tests/test_audit_regressions.py section 16
// holds it to that with no 404.html on disk.
const indexHtml = join(distDir, "index.html");
if (existsSync(indexHtml)) {
  copyFileSync(indexHtml, join(distDir, "404.html"));
}
