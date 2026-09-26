import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

// Monitoring builds simple time-bucketed traffic/threat trends from the recent
// threat list plus the metrics summary.
export function Monitoring({ metrics, threats }) {
  const series = buildSeries(threats);
  return (
    <div>
      <div className="panel">
        <h2>Threat Activity (recent)</h2>
        {series.length === 0 ? (
          <div className="empty">No threat activity to plot yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#26304a" />
              <XAxis dataKey="t" stroke="#8a97b1" fontSize={11} />
              <YAxis stroke="#8a97b1" fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#1b2333", border: "1px solid #26304a" }} />
              <Legend />
              <Line type="monotone" dataKey="blocked" stroke="#e74c3c" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="rate_limited" stroke="#f39c12" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="escalated" stroke="#3498db" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="grid">
        <div className="card">
          <div className="label">Avg Latency (ms)</div>
          <div className="value blue">{metrics.avg_latency_ms ?? 0}</div>
        </div>
        <div className="card">
          <div className="label">Total Requests</div>
          <div className="value">{metrics.total_requests ?? 0}</div>
        </div>
        <div className="card">
          <div className="label">Active Threats</div>
          <div className="value red">{metrics.active_threats ?? 0}</div>
        </div>
        <div className="card">
          <div className="label">Threat Rate</div>
          <div className="value amber">{threatRate(metrics)}%</div>
        </div>
      </div>
    </div>
  );
}

function buildSeries(threats) {
  if (!threats || threats.length === 0) return [];
  const buckets = {};
  for (const t of threats) {
    const key = (t.timestamp || "").slice(11, 16) || "?";
    buckets[key] = buckets[key] || {
      t: key,
      blocked: 0,
      rate_limited: 0,
      escalated: 0,
    };
    if (t.action === "BLOCK") buckets[key].blocked += 1;
    else if (t.action === "RATE_LIMIT") buckets[key].rate_limited += 1;
    else if (t.action === "ESCALATE") buckets[key].escalated += 1;
  }
  return Object.values(buckets).sort((a, b) => a.t.localeCompare(b.t));
}

function threatRate(metrics) {
  const total = metrics.total_requests || 0;
  if (!total) return 0;
  return (((metrics.active_threats || 0) / total) * 100).toFixed(1);
}
