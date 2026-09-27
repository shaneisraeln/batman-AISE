import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Feedback } from "../components/Feedback.jsx";
import { ThreatDetail } from "../components/ThreatDetail.jsx";
import { Analytics } from "../components/Analytics.jsx";
import { setToken } from "../api.js";
import { installFetch } from "./mockApi.js";

beforeEach(() => setToken("tok_test"));

describe("Feedback page", () => {
  it("shows an honest empty state when there is no feedback", async () => {
    installFetch({ "GET /v1/feedback": { feedback: [] } });
    render(<Feedback />);
    expect(await screen.findByText(/No feedback yet/i)).toBeInTheDocument();
  });

  it("lists tenant-scoped feedback rows", async () => {
    installFetch({
      "GET /v1/feedback": {
        feedback: [
          {
            request_id: "req_1",
            label: "TRUE_POSITIVE",
            analyst_note: "confirmed probe",
            created_at: "2026-01-01T00:00:00Z",
            threat_type: "MODEL_EXTRACTION",
          },
        ],
      },
    });
    render(<Feedback />);
    expect(await screen.findByText("confirmed probe")).toBeInTheDocument();
    expect(screen.getAllByText("TRUE_POSITIVE").length).toBeGreaterThan(0);
    expect(screen.getByText("req_1")).toBeInTheDocument();
  });
});

describe("ThreatDetail feedback submit", () => {
  it("posts a verdict to /v1/feedback and re-fetches the detail", async () => {
    let submitted = false;
    const detail = {
      request_id: "req_9",
      threat_type: "MODEL_EXTRACTION",
      threat_level: "HIGH",
      action: "BLOCK",
      anomaly_score: 0.9,
      extraction_score: 0.8,
      latency_ms: 12,
      detector_version: "1.0",
      session_id: "s1",
      reason: "systematic probing",
      features: { request_rate: 42 },
      feedback: [],
    };
    const mock = installFetch({
      "GET /v1/threats/req_9": () =>
        submitted
          ? { ...detail, feedback: [{ label: "TRUE_POSITIVE", analyst_note: "logged" }] }
          : detail,
      "POST /v1/feedback": () => {
        submitted = true;
        return { status: "recorded", request_id: "req_9" };
      },
    });

    render(<ThreatDetail requestId="req_9" onBack={() => {}} />);
    const user = userEvent.setup();

    // Detail loads.
    await waitFor(() => expect(screen.getByText("systematic probing")).toBeInTheDocument());

    // Submit a TRUE_POSITIVE verdict.
    await user.click(screen.getByRole("button", { name: "TRUE_POSITIVE" }));

    await waitFor(() => expect(screen.getByText(/justice served/i)).toBeInTheDocument());
    expect(mock.lastBody("POST", "/v1/feedback")).toMatchObject({
      request_id: "req_9",
      label: "TRUE_POSITIVE",
    });
  });
});

describe("Analytics", () => {
  it("shows an honest empty state with no traffic", () => {
    render(<Analytics metrics={{ total_requests: 0 }} threats={[]} />);
    expect(screen.getByText(/No traffic yet/i)).toBeInTheDocument();
  });

  it("renders KPIs and threat breakdown when there is traffic", () => {
    const metrics = {
      total_requests: 200,
      allowed: 150,
      blocked: 15,
      rate_limited: 5, // enforced = 20/200 = 10.0%
      active_threats: 30, // flagged = 30/200 = 15.0%
      avg_latency_ms: 12.3,
      actions: { ALLOW: 150, BLOCK: 15, RATE_LIMIT: 5 },
      threat_categories: { MODEL_EXTRACTION: 20, ANOMALOUS_INPUT: 10 },
    };
    const threats = [
      { request_id: "r1", threat_type: "MODEL_EXTRACTION", threat_level: "HIGH" },
      { request_id: "r2", threat_type: "ANOMALOUS_INPUT", threat_level: "MEDIUM" },
    ];
    render(<Analytics metrics={metrics} threats={threats} />);

    // KPI: enforced% = (15+5)/200 = 10.0%, flagged% = 30/200 = 15.0%
    expect(screen.getByText("10.0%")).toBeInTheDocument();
    expect(screen.getByText("15.0%")).toBeInTheDocument();
    // Threat type table lists categories.
    expect(screen.getByText("MODEL_EXTRACTION")).toBeInTheDocument();
    expect(screen.getByText("ANOMALOUS_INPUT")).toBeInTheDocument();
  });
});
