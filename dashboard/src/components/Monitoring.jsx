import React from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { IDLE_LINES, pick } from "./eggs.js";

const AXIS = { stroke: "#3a3a3a", fontSize: 10, fontFamily: "JetBrains Mono" };

export function Monitoring({ metrics, threats = [] }) {
  const series = buildSeries(threats);

  return (
    <div>
      <div className="section-head">
        <h2>The Watch</h2>
        <span className="hint">rolling activity · updates every 3s</span>
      </div>

      <div className="panel full" style={{ marginBottom: 22 }}>
        <div className="phead">Threat Activity</div>
        <div className="pbody">
          {series.length === 0 ? (
            <div className="empty">
              <div className="glyph">🦇</div>
              {pick(IDLE_LINES)}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="gBlock" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#c0392b" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#c0392b" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gRate" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#b8862b" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#b8862b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" {...AXIS} />
                <YAxis {...AXIS} allowDecimals={false} />
                <Tooltip />
                <Legend wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: 10 }} />
                <Area type="monotone" dataKey="blocked" stroke="#c0392b" fill="url(#gBlock)" strokeWidth={1.5} />
                <Area type="monotone" dataKey="rate_limited" stroke="#b8862b" fill="url(#gRate)" strokeWidth={1.5} />
                <Line type="monotone" dataKey="escalated" stroke="#4a6b8a" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="kpis">
        <Stat label="Avg Latency" value={`${metrics.avg_latency_ms ?? 0}ms`} />
        <Stat label="Total Requests" value={metrics.total_requests ?? 0} />
        <Stat label="Active Threats" value={metrics.active_threats ?? 0} cls="amber" />
        <Stat label="Threat Rate" value={`${threatRate(metrics)}%`} cls="warn" />
      </div>
    </div>
  );
}

function Stat({ label, value, cls = "" }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${cls}`}>{value}</div>
    </div>
  );
}

function buildSeries(threats) {
  if (!threats.length) return [];
  const b = {};
  for (const t of threats) {
    const key = (t.timestamp || "").slice(11, 16) || "?";
    b[key] = b[key] || { t: key, blocked: 0, rate_limited: 0, escalated: 0 };
    if (t.action === "BLOCK") b[key].blocked++;
    else if (t.action === "RATE_LIMIT") b[key].rate_limited++;
    else if (t.action === "ESCALATE") b[key].escalated++;
  }
  return Object.values(b).sort((a, z) => a.t.localeCompare(z.t));
}
function threatRate(m) {
  const total = m.total_requests || 0;
  if (!total) return 0;
  return (((m.active_threats || 0) / total) * 100).toFixed(1);
}
