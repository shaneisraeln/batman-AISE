// A small fetch router for tests. It matches "METHOD /path" (query string
// stripped) against a routes map and returns canned JSON, mirroring the real
// BATMAN cloud API contract. Route values may be a static object or a function
// (body, {method, path}) => object | {status, body} for status control.
//
// This keeps component tests honest: they exercise the exact api.js code paths
// (fetch URL, method, Authorization / Content-Type headers, JSON parsing) that
// run against the live backend — only the network boundary is stubbed.

import { vi } from "vitest";

export function installFetch(routes) {
  const calls = [];

  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase();
    const path = String(url).split("?")[0];
    const key = `${method} ${path}`;
    calls.push({ method, path, key, headers: opts.headers || {}, body: parse(opts.body) });

    let entry = routes[key];
    if (entry === undefined) {
      // Unknown route -> 404 so tests fail loudly instead of hanging.
      return jsonResponse(404, { detail: `no mock for ${key}` });
    }
    if (typeof entry === "function") {
      entry = entry(parse(opts.body), { method, path });
    }
    if (entry && typeof entry === "object" && "status" in entry && "body" in entry) {
      return jsonResponse(entry.status, entry.body);
    }
    return jsonResponse(200, entry);
  });

  return {
    calls,
    called: (method, path) =>
      calls.some((c) => c.method === method.toUpperCase() && c.path === path),
    lastBody: (method, path) => {
      const hit = [...calls].reverse().find(
        (c) => c.method === method.toUpperCase() && c.path === path
      );
      return hit ? hit.body : undefined;
    },
  };
}

function parse(body) {
  if (!body) return undefined;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    headers: { get: () => null },
  };
}
