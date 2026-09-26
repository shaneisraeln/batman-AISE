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
  CartesianGrid,
} from "recharts";
import { StatCards } from "./StatCards.jsx";

const COLORS = ["#f5c518", "#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12"];

export function Overview({ metrics }) {
  const actionData = Object.entries(metrics.actions || {}).map(([k, v]) => ({
    name: k,
    count: v,
  }));
  const threatData = Object.entries(metrics.threat_categories || {}).map(
    ([k, v]) => ({ name: k, value: v })
  );

  return (
    <div>
      <StatCards metrics={metrics} />
      <div className="detail-grid">
        <div className="panel">
          <h2>Actions Taken</h2>
          {actionData.length === 0 ? (
            <div className="empty">No traffic yet. Run the demo simulator.</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={actionData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#26304a" />
                <XAxis dataKey="name" stroke="#8a97b1" fontSize={11} />
                <YAxis stroke="#8a97b1" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#1b2333", border: "1px solid #26304a" }}
                />
                <Bar dataKey="count" fill="#f5c518" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="panel">
          <h2>Threat Categories</h2>
          {threatData.length === 0 ? (
            <div className="empty">No threats detected yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={threatData}
                  dataKey="value"
                  nameKey="name"
                  outerRadius={95}
                  label={(e) => e.name}
                >
                  {threatData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "#1b2333", border: "1px solid #26304a" }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
