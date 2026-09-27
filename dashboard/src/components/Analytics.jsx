import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// Analytics view — a focused, honest read of the tenant's own telemetry.
//
// Everything here derives from real backend data passed down from App:
//   - metrics  <- GET /v1/metrics  (tenant-scoped aggregate)
//   - threats  <- GET /v1/threats  (tenant-scoped recent detections)
//
// There is no synthetic or illustrative data. When a tenant has no traffic
// yet, we say so plainly instead of drawing an empty-but-official-looking chart.

const AXIS = { stroke: "#3a3a3a", fontSize: 10, fontFamily: "JetBrains Mono" };

const THREAT_COLORS = {
  MODEL_EXTRACTION: "#f2c14e",
  ANOMALOUS_INPUT: "#c0392b",
  API_ABUSE: "#b8862b",
  INVALID_REQUEST: "#4a6b8a",
};

export function Analytics({ metrics = {}, threats = [] }) {
  const total = metrics.total_requests ?? 0;

  if (!total) {
    return (
      <div>
        <div className="section-head">
          <h2>Analytics</h2>
          <span className="hint">tenant-scoped</span>
        </div>
        <div className="panel">
          <div className="empty">
            <div className="glyph">🦇</div>
            No traffic yet. Once requests flow through your protected models,
            detection rates, threat mix, and enforcement outcomes appear here —
            computed from your telemetry only.
          </div>
        </div>
      </div>
    );
  }

  const blocked = metrics.blocked ?? 0;
  const rateLimited = metrics.rate_limited ?? 0;
  const allowed = metrics.allowed ?? 0;
  const activeThreats = metrics.active_threats ?? 0;

  const enforcedPct = total ? (((blocked + rateLimited) / total) * 100).toFixed(1) : "0.0";
  const threatPct = total ? ((activeThreats / total) * 100).toFixed(1) : "0.0";

  const actionData = Object.entries(metrics.actions || {}).map(([name, count]) => ({
    name,
    count,
  }));
  const threatData = Object.entries(metrics.threat_categories || {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  // Threat-level breakdown is derived from the recent threats list (the only
  // place level is available per-request). Labelled as "recent" so it is not
  // mistaken for an all-time figure.
  const levelCounts = {};
  for (const t of threats) {
    const lvl = t.threat_level || "UNKNOWN";
    levelCounts[lvl] = (levelCounts[lvl] || 0) + 1;
  }
  const levelData = Object.entries(levelCounts).map(([name, value]) => ({ name, value }));

  const kpis = [
    { label: "Total Requests", value: total },
    { label: "Enforced", value: `${enforcedPct}%`, cls: "danger", foot: "blocked + rate-limited" },
    { label: "Flagged Threats", value: `${threatPct}%`, cls: "amber", foot: "of all requests" },
    { label: "Avg Latency", value: `${metrics.avg_latency_ms ?? 0}ms`, foot: "per decision" },
  ];

  return (
    <div>
      <div className="section-head">
        <h2>Analytics</h2>
        <span className="hint">tenant-scoped · derived from your telemetry</span>
      </div>

      <div className="kpis">
        {kpis.map((k) => (
          <div className="kpi" key={k.label}>
            <div className="label">{k.label}</div>
            <div className={`value ${k.cls || ""}`}>{k.value}</div>
            {k.foot && <div className="foot">{k.foot}</div>}
          </div>
        ))}
      </div>

      <div className="panels">
        <div className="panel">
          <div className="phead">Enforcement Outcomes</div>
          <div className="pbody">
            {actionData.length === 0 ? (
              <Empty />
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={actionData}>
                  <XAxis dataKey="name" {...AXIS} />
                  <YAxis {...AXIS} allowDecimals={false} />
                  <Tooltip cursor={{ fill: "rgba(242,193,78,0.05)" }} />
                  <Bar dataKey="count" fill="#f2c14e" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="phead">Threat Types (all-time)</div>
          <div className="pbody" style={{ padding: 0 }}>
            {threatData.length === 0 ? (
              <div className="empty" style={{ padding: 30 }}>
                No threats detected yet — allowed traffic only.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Threat Type</th>
                    <th style={{ textAlign: "right" }}>Count</th>
                    <th style={{ textAlign: "right" }}>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {threatData.map((d) => (
                    <tr key={d.name}>
                      <td>
                        <span
                          className="dotmark"
                          style={{ background: THREAT_COLORS[d.name] || "#3a3a3a" }}
                        />
                        {d.name}
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {d.value}
                      </td>
                      <td className="faint mono" style={{ textAlign: "right" }}>
                        {((d.value / activeThreats) * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="panel full">
          <div className="phead">
            Threat Severity
            <span className="faint">recent {threats.length} detections</span>
          </div>
          <div className="pbody">
            {levelData.length === 0 ? (
              <Empty />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={levelData} layout="vertical">
                  <XAxis type="number" {...AXIS} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" {...AXIS} width={90} />
                  <Tooltip cursor={{ fill: "rgba(242,193,78,0.05)" }} />
                  <Bar dataKey="value" fill="#b8862b" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Empty() {
  return <div className="empty">Nothing to chart yet.</div>;
}
