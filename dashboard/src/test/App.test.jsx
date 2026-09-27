import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App.jsx";
import { setToken, getToken } from "../api.js";
import { installFetch } from "./mockApi.js";

// Baseline monitoring responses the authed dashboard polls on mount.
const EMPTY_MONITORING = {
  "GET /v1/metrics": { total_requests: 0, actions: {}, threat_categories: {} },
  "GET /v1/threats": { threats: [] },
  "GET /v1/health": { status: "ok", mode: "cloud", detector_ready: true, llm_provider: "stub" },
  "GET /auth/me": { user_id: "u1", email: "a@b.com", display_name: "A" },
};

describe("App auth gate", () => {
  it("shows the login screen when there is no token", async () => {
    installFetch({});
    render(<App />);
    // The auth card sign-in / sign-up tabs are present.
    expect(await screen.findByText("Sign In")).toBeInTheDocument();
    expect(screen.getByText("Sign Up")).toBeInTheDocument();
  });

  it("opens the sign-up tab when the route is #/signup", async () => {
    window.location.hash = "#/signup";
    installFetch({});
    render(<App />);
    // Signup mode reveals the optional name field.
    expect(await screen.findByPlaceholderText("name (optional)")).toBeInTheDocument();
  });

  it("logs in, lands on the dashboard, then logs out back to login", async () => {
    const mock = installFetch({
      "POST /auth/login": { token: "tok_login" },
      ...EMPTY_MONITORING,
    });
    render(<App />);
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText("email"), "a@b.com");
    await user.type(screen.getByPlaceholderText("password (min 8 chars)"), "password123");
    await user.click(screen.getByRole("button", { name: /Enter the Batcave/i }));

    // Dashboard chrome appears (sidebar nav groups).
    await waitFor(() => expect(screen.getByText("Monitor")).toBeInTheDocument());
    expect(getToken()).toBe("tok_login");
    expect(mock.called("POST", "/auth/login")).toBe(true);

    // Navigate to Settings and sign out.
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(await screen.findByRole("button", { name: /Sign out/i }));

    // Back at the login screen; token cleared.
    await waitFor(() => expect(screen.getByText("Sign In")).toBeInTheDocument());
    expect(getToken()).toBeNull();
  });

  it("renders the dashboard directly when a token already exists", async () => {
    setToken("tok_existing");
    installFetch(EMPTY_MONITORING);
    render(<App />);
    await waitFor(() => expect(screen.getByText("Monitor")).toBeInTheDocument());
    // New nav sections from Phase 2B are present.
    expect(screen.getByRole("button", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Feedback" })).toBeInTheDocument();
  });
});
