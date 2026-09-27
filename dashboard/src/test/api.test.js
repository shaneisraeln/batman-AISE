import { describe, it, expect } from "vitest";
import { api, getToken, isAuthed, setToken } from "../api.js";
import { installFetch } from "./mockApi.js";

describe("api.js client", () => {
  it("login stores the returned token and marks the session authed", async () => {
    installFetch({ "POST /auth/login": { token: "tok_abc" } });
    expect(isAuthed()).toBe(false);
    const r = await api.login("a@b.com", "password123");
    expect(r.token).toBe("tok_abc");
    expect(getToken()).toBe("tok_abc");
    expect(isAuthed()).toBe(true);
  });

  it("signup stores the token too", async () => {
    installFetch({ "POST /auth/signup": { token: "tok_new" } });
    await api.signup("new@b.com", "password123", "New");
    expect(getToken()).toBe("tok_new");
  });

  it("logout clears the token", async () => {
    setToken("tok_x");
    expect(isAuthed()).toBe(true);
    api.logout();
    expect(getToken()).toBeNull();
    expect(isAuthed()).toBe(false);
  });

  it("attaches the Bearer token on authed requests", async () => {
    setToken("tok_bearer");
    const mock = installFetch({ "GET /projects": { projects: [] } });
    await api.projects();
    const call = mock.calls.find((c) => c.path === "/projects");
    expect(call.headers.Authorization).toBe("Bearer tok_bearer");
  });

  it("feedback posts to /v1/feedback with the expected body", async () => {
    setToken("tok_fb");
    const mock = installFetch({ "POST /v1/feedback": { status: "recorded" } });
    await api.feedback("req_1", "TRUE_POSITIVE", "note");
    expect(mock.lastBody("POST", "/v1/feedback")).toEqual({
      request_id: "req_1",
      label: "TRUE_POSITIVE",
      analyst_note: "note",
    });
  });

  it("clears the token and throws 'unauthorized' on a 401", async () => {
    setToken("tok_expired");
    installFetch({ "GET /v1/metrics": { status: 401, body: { detail: "expired" } } });
    await expect(api.metrics()).rejects.toThrow("unauthorized");
    expect(getToken()).toBeNull();
  });
});
