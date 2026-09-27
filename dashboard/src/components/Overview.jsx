import React from "react";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { IDLE_LINES, pick } from "./eggs.js";

const AXIS = { stroke: "#3a3a3a", fontSize: 10, fontFamily: "JetBrains Mono" };
const THREAT_COLORS = {
  MODEL_EXTRACTION: "#f2c14e",
  ANOMALOUS_INPUT: "#c0392b",
  API_ABUSE: "#b8862b",
  INVALID_REQUEST: "#4a6b8a",
};

export function Overview({ metrics, threats = [], onSelect }) {
  const total = metrics.total_requests ?? 0;
  const kpis = [
    { label: "Total Requests", value: total, cls: "" },
    { label: "Allowed", value: metrics.allowed ?? 0, cls: "ok", foot: "passed the watch" },
    { label: "Rate Limited", value: metrics.rate_limited ?? 0, cls: "warn", foot: "slowed down" },
    { label: "Blocked", value: metrics.blocked ?? 0, cls: "danger", foot: "denied entry" },
    { label: "Active Threats", value: metrics.active_threats ?? 0, cls: "amber" },
    { label: "Escalated", value: metrics.escalated ?? 0, cls: "" },
    { label: "Avg Latency", value: `${metrics.avg_latency_ms ?? 0}ms`, cls: "", foot: "per decision" },
    {
      label: "Threat Types",
      value: Object.keys(metrics.threat_categories || {}).length,
      cls: "",
    },
  ];

  const actionData = Object.entries(metrics.actions || {}).map(([name, count]) => ({
    name,
    count,
  }));
  const threatData = Object.entries(metrics.threat_categories || {}).map(
    ([name, value]) => ({ name, value })
  );
  const recent = threats.slice(0, 8);

  return (
    <div>
      <div className="kpis">
        {kpis.map((k) => (
          <div className="kpi" key={k.label}>
            <div className="label">{k.label}</div>
            <div className={`value ${k.cls}`}>{k.value}</div>
            {k.foot && <div className="foot">{k.foot}</div>}
          </div>
        ))}
      </div>

      <div className="panels">
        <div className="panel">
          <div className="phead">Actions Taken</div>
          <div className="pbody">
            {actionData.length === 0 ? (
              <Idle />
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
          <div className="phead">Threat Categories</div>
          <div className="pbody">
            {threatData.length === 0 ? (
              <Idle />
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <PieChart>
                  <Pie
                    data={threatData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={52}
                    outerRadius={88}
                    paddingAngle={2}
                    stroke="#000"
                  >
                    {threatData.map((d) => (
                      <Cell key={d.name} fill={THREAT_COLORS[d.name] || "#3a3a3a"} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="panel full">
          <div className="phead">
            Recent Activity
            <span className="faint">{recent.length ? "live feed" : ""}</span>
          </div>
          <div className="pbody" style={{ padding: 0 }}>
            {recent.length === 0 ? (
              <Idle />
            ) : (
              <table className="tbl">
                <tbody>
                  {recent.map((t) => (
                    <tr
                      key={t.request_id}
                      className="row"
                      onClick={() => onSelect && onSelect(t.request_id)}
                    >
                      <td className="faint mono" style={{ width: 90 }}>
                        {fmtTime(t.timestamp)}
                      </td>
                      <td>
                        <span className={`tick ${t.threat_level}`}>{t.threat_type}</span>
                      </td>
                      <td className="muted mono">{t.session_id}</td>
                      <td style={{ textAlign: "right" }}>
                        <span className={`act ${t.action}`}>{t.action}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Idle() {
  return (
    <div className="empty">
      <div className="glyph">🦇</div>
      {pick(IDLE_LINES)}
    </div>
  );
}

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString([], { hour12: false });
  } catch {
    return "—";
  }
}
