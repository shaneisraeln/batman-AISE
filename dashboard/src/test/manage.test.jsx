import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Projects } from "../components/Projects.jsx";
import { Models } from "../components/Models.jsx";
import { ApiKeys } from "../components/ApiKeys.jsx";
import { setToken } from "../api.js";
import { installFetch } from "./mockApi.js";

beforeEach(() => setToken("tok_test"));

describe("Projects", () => {
  it("creates a project and reloads the list", async () => {
    let created = false;
    const mock = installFetch({
      "GET /projects": () =>
        created
          ? { projects: [{ project_id: "p1", name: "Fraud", environment: "production", created_at: "2026-01-01" }] }
          : { projects: [] },
      "POST /projects": () => {
        created = true;
        return { project_id: "p1", name: "Fraud", environment: "production" };
      },
    });
    render(<Projects />);
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText("project name"), "Fraud");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(screen.getByText("Fraud")).toBeInTheDocument());
    expect(mock.lastBody("POST", "/projects")).toMatchObject({ name: "Fraud" });
  });
});

describe("Models", () => {
  it("registers a model under the selected project", async () => {
    let registered = false;
    const mock = installFetch({
      "GET /projects": { projects: [{ project_id: "p1", name: "Fraud", environment: "production" }] },
      "GET /models": () =>
        registered
          ? { models: [{ model_id: "m1", project_id: "p1", name: "v1", status: "active" }] }
          : { models: [] },
      "POST /models": () => {
        registered = true;
        return { model_id: "m1", project_id: "p1", name: "v1" };
      },
    });
    render(<Models />);
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByPlaceholderText("model name")).toBeInTheDocument());
    await user.type(screen.getByPlaceholderText("model name"), "v1");
    await user.click(screen.getByRole("button", { name: "Register" }));

    await waitFor(() => expect(screen.getByText("v1")).toBeInTheDocument());
    expect(mock.lastBody("POST", "/models")).toMatchObject({ project_id: "p1", name: "v1" });
  });
});

describe("ApiKeys", () => {
  it("shows a new key exactly once, then lists metadata and revokes", async () => {
    let keys = [];
    const mock = installFetch({
      "GET /keys": () => ({ api_keys: keys }),
      "GET /projects": { projects: [{ project_id: "p1", name: "Fraud" }] },
      "GET /models": { models: [{ model_id: "m1", project_id: "p1", name: "v1" }] },
      "POST /keys": () => {
        keys = [
          { key_id: "k1", name: "prod", model_id: "m1", status: "active", created_at: "2026-01-01", last_used_at: null },
        ];
        return { api_key: "bm_live_secretonce", key_id: "k1" };
      },
      "DELETE /keys/k1": () => {
        keys = [
          { key_id: "k1", name: "prod", model_id: "m1", status: "revoked", created_at: "2026-01-01", last_used_at: null },
        ];
        return { status: "revoked", key_id: "k1" };
      },
    });
    render(<ApiKeys />);
    const user = userEvent.setup();

    // Select a model then generate. Two selects exist (project, model);
    // the model select is the second combobox.
    await waitFor(() => expect(screen.getByText("select model…")).toBeInTheDocument());
    const combos = screen.getAllByRole("combobox");
    await user.selectOptions(combos[1], "m1");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    // Raw key shown exactly once.
    expect(await screen.findByText("bm_live_secretonce")).toBeInTheDocument();

    // Dismiss the reveal — the raw key must be gone afterward.
    await user.click(screen.getByRole("button", { name: "dismiss" }));
    await waitFor(() =>
      expect(screen.queryByText("bm_live_secretonce")).not.toBeInTheDocument()
    );

    // Revoke the active key.
    await user.click(await screen.findByRole("button", { name: "revoke" }));
    await waitFor(() => expect(screen.getByText("revoked")).toBeInTheDocument());
    expect(mock.called("DELETE", "/keys/k1")).toBe(true);
  });
});
