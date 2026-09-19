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
    renameSync(join(clientDir, entry), join(distDir, entry));
  }
  rmSync(clientDir, { recursive: true, force: true });
}

// This app has client-side routes beyond "/" (/maintenance,
// /maintenance/tickets/$id/{-$section}, /properties/...), but FastAPI's
// current mount -- app.mount("/", StaticFiles(directory=..., html=True)) in
// backend/app/main.py -- does NOT catch-all unmatched paths to index.html;
// Starlette's html=True mode only serves 404.html on a miss (else a plain
// 404). Without this, refreshing or deep-linking to any route other than
// "/" 404s instead of reaching the SPA shell. Shipping the shell as
// dist/404.html too (the same trick GitHub Pages/Netlify use) makes that
// existing mount serve it -- with a 404 status, which the browser still
// renders and hydrates normally -- for every unmatched path, no backend
// change required. If a future phase changes the mount to a real catch-all
// route, this file becomes redundant but harmless.
const indexHtml = join(distDir, "index.html");
if (existsSync(indexHtml)) {
  copyFileSync(indexHtml, join(distDir, "404.html"));
}
