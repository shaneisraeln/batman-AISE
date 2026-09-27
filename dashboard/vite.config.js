/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the BATMAN Cloud API (Phase 2). In dev, proxy the
// control-plane and data-plane paths to the cloud API so the frontend can use
// relative URLs with no CORS surprises.
const CLOUD = process.env.BATMAN_CLOUD_URL || "http://localhost:8100";

export default defineConfig({
  // Served at "/" in dev; set VITE_BASE=/app/ when deployed behind the proxy.
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: CLOUD, changeOrigin: true },
      "/auth": { target: CLOUD, changeOrigin: true },
      "/projects": { target: CLOUD, changeOrigin: true },
      "/models": { target: CLOUD, changeOrigin: true },
      "/keys": { target: CLOUD, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    css: false,
  },
});
