import { defineConfig } from "vite";

// The frontend lives in ui/ (kept separate from src-tauri/ and node_modules/
// so Tauri's frontendDist never walks the Rust build output — see the
// "Networking detail" / folder-layout note in README.md's history for why).
//
// Fixed, non-default port so Tauri's dev supervisor always finds it at a
// known address, and so it never collides with the main LPM web frontend's
// own Vite dev server (that one runs on 5173 — see ../frontend).
export default defineConfig({
  root: "ui",
  server: {
    port: 1420,
    strictPort: true,
  },
  // Baked into the shell's settings footer (ui/src/main.js) so an installed
  // build can be traced back to the exact commit it came from. The GitHub
  // Actions release workflow sets LPM_BUILD_SHA to the short commit SHA
  // before `tauri build` — see md/desktop_app_CI_github.md. Local dev/build
  // runs leave it unset, which the shell renders as "dev".
  define: {
    __LPM_BUILD_SHA__: JSON.stringify(process.env.LPM_BUILD_SHA || "dev"),
  },
});
