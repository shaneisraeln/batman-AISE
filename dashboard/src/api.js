// Thin client for the BATMAN gateway API.
const BASE = import.meta.env.VITE_API_BASE || "";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get("/v1/health"),
  metrics: () => get("/v1/metrics"),
  threats: (limit = 100) => get(`/v1/threats?limit=${limit}`),
  threatDetail: (id) => get(`/v1/threats/${id}`),
  feedback: (request_id, label, analyst_note = "") =>
    post("/v1/feedback", { request_id, label, analyst_note }),
};
