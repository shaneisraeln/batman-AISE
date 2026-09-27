// BATMAN Cloud API client (Phase 2).
//
// Talks to the multi-tenant cloud API. Control-plane calls use a Bearer token
// obtained at login; the token is stored in localStorage. All dashboard data is
// real — fetched from the backend, never fabricated.

const BASE = import.meta.env.VITE_API_BASE || "";
const TOKEN_KEY = "batman_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}
export function isAuthed() {
  return !!getToken();
}

function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}`, ...extra } : extra;
}

async function handle(res, path) {
  if (res.status === 401) {
    // Token invalid/expired — force re-login.
    setToken(null);
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = JSON.stringify((await res.json()).detail || "");
    } catch {
      /* ignore */
    }
    throw new Error(`${path} -> ${res.status} ${detail}`);
  }
  return res.json();
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  return handle(res, path);
}
async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return handle(res, path);
}
async function put(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return handle(res, path);
}
async function del(path) {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res, path);
}

export const api = {
  // auth
  async signup(email, password, display_name) {
    const r = await post("/auth/signup", { email, password, display_name });
    setToken(r.token);
    return r;
  },
  async login(email, password) {
    const r = await post("/auth/login", { email, password });
    setToken(r.token);
    return r;
  },
  logout() {
    setToken(null);
  },
  me: () => get("/auth/me"),

  // projects / models / keys
  projects: () => get("/projects"),
  createProject: (name, environment) => post("/projects", { name, environment }),
  models: (project_id) => get(`/models${project_id ? `?project_id=${project_id}` : ""}`),
  registerModel: (project_id, name) => post("/models", { project_id, name }),
  keys: () => get("/keys"),
  createKey: (project_id, model_id, name) => post("/keys", { project_id, model_id, name }),
  revokeKey: (key_id) => del(`/keys/${key_id}`),
  setUpstream: (model_id, cfg) => put(`/models/${model_id}/upstream`, cfg),

  // monitoring (tenant-scoped, Bearer)
  health: () => get("/v1/health"),
  metrics: () => get("/v1/metrics"),
  threats: (limit = 200) => get(`/v1/threats?limit=${limit}`),
  threatDetail: (id) => get(`/v1/threats/${id}`),

  // analyst feedback (tenant-scoped, Bearer)
  feedback: (request_id, label, analyst_note) =>
    post("/v1/feedback", { request_id, label, analyst_note: analyst_note || null }),
  listFeedback: (limit = 200) => get(`/v1/feedback?limit=${limit}`),
};
