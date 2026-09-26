import React from "react";

export function StatCards({ metrics }) {
  const cards = [
    { label: "Total Requests", value: metrics.total_requests ?? 0, cls: "" },
    { label: "Allowed", value: metrics.allowed ?? 0, cls: "green" },
    { label: "Rate Limited", value: metrics.rate_limited ?? 0, cls: "amber" },
    { label: "Blocked", value: metrics.blocked ?? 0, cls: "red" },
    { label: "Active Threats", value: metrics.active_threats ?? 0, cls: "red" },
    { label: "Escalated", value: metrics.escalated ?? 0, cls: "blue" },
    {
      label: "Avg Latency (ms)",
      value: metrics.avg_latency_ms ?? 0,
      cls: "blue",
    },
    {
      label: "Threat Types",
      value: Object.keys(metrics.threat_categories || {}).length,
      cls: "",
    },
  ];
  return (
    <div className="grid">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="label">{c.label}</div>
          <div className={`value ${c.cls}`}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}
