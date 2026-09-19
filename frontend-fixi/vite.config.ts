import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import viteTsConfigPaths from "vite-tsconfig-paths";

// Plain Vite + TanStack Start config (SPA mode). Mirrors frontend/vite.config.ts's
// conventions: no sandbox/proxy detection, no Cloudflare/Nitro deployment target --
// `vite build` produces a static dist/ that FastAPI can mount with StaticFiles,
// the same way it already mounts frontend/dist.
export default defineConfig({
  plugins: [
    viteTsConfigPaths({ projects: ["./tsconfig.json"] }),
    tailwindcss(),
    tanstackStart({
      // No server functions/routes are used anywhere in this app (mock data only),
      // so SPA mode's prerendered shell + client-side router is all we need --
      // no Nitro server has to run at request time.
      spa: {
        enabled: true,
        prerender: {
          // Default outputPath is /_shell.html; write it to the conventional
          // index.html instead so the static bundle matches frontend/dist's
          // shape (index.html + assets/) and "just works" behind a plain
          // static file server / StaticFiles(html=True) mount.
          outputPath: "/index.html",
        },
      },
    }),
    viteReact(),
  ],
  server: {
    port: 5174,
  },
});
