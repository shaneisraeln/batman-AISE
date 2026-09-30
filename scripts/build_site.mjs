#!/usr/bin/env node
/**
 * Assemble the single-origin public site for one Vercel deployment:
 *
 *   public_site/                 (final output, served by Vercel)
 *     index.html   landing.css   (from landing/)
 *     docs/                       (from landing/docs/)
 *     app/                        (the Vite dashboard, built with base=/app/)
 *
 * This makes the landing CTAs (which link to /app/#/signup and /app/#/login)
 * live links on the same origin — the whole product is one deployment.
 *
 * Steps:
 *   1. build the dashboard with VITE_BASE=/app/  -> dashboard/dist
 *   2. copy landing/ -> public_site/
 *   3. copy dashboard/dist -> public_site/app/
 *
 * VITE_API_BASE (the Render backend URL) is read from the environment at build
 * time and baked into the dashboard bundle (see dashboard/src/api.js).
 *
 * Usage:  node scripts/build_site.mjs
 */

import { execSync } from "node:child_process";
import { cpSync, rmSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "public_site");
const dashboard = resolve(root, "dashboard");
const landing = resolve(root, "landing");

function run(cmd, cwd) {
  console.log(`\n$ ${cmd}  (cwd=${cwd})`);
  execSync(cmd, { cwd, stdio: "inherit", env: { ...process.env, VITE_BASE: "/app/" } });
}

// 0) clean output
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

// 1) install + build dashboard with base=/app/
if (!existsSync(resolve(dashboard, "node_modules"))) {
  run("npm install --no-audit --no-fund", dashboard);
}
run("npm run build", dashboard); // vite reads VITE_BASE=/app/ from env

// 2) copy landing to output root (index.html, landing.css, docs/)
cpSync(landing, out, { recursive: true });
// The landing Dockerfile is irrelevant to a static host; drop it if copied.
rmSync(resolve(out, "Dockerfile"), { force: true });

// 3) copy the built dashboard under /app/
cpSync(resolve(dashboard, "dist"), resolve(out, "app"), { recursive: true });

console.log(`\n✓ Public site assembled at: ${out}`);
console.log("  /            -> landing");
console.log("  /docs/       -> docs");
console.log("  /app/        -> dashboard SPA (base=/app/)");
