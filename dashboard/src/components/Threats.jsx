import React, { useMemo, useState } from "react";
import { pick, IDLE_LINES } from "./eggs.js";

const COLUMNS = [
  { key: "timestamp", label: "Time" },
  { key: "threat_type", label: "Threat" },
  { key: "threat_level", label: "Level" },
  { key: "anomaly_score", label: "Anomaly" },
  { key: "extraction_score", label: "Extraction" },
  { key: "action", label: "Action" },
  { key: "session_id", label: "Session" },
];

const FILTERS = ["ALL", "BLOCK", "RATE_LIMIT", "ESCALATE", "LOG"];

export function Threats({ threats = [], onSelect }) {
  const [sort, setSort] = useState({ key: "timestamp", dir: "desc" });
  const [filter, setFilter] = useState("ALL");
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    let r = [...threats];
    if (filter !== "ALL") r = r.filter((t) => t.action === filter);
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter(
        (t) =>
          (t.threat_type || "").toLowerCase().includes(s) ||
          (t.session_id || "").toLowerCase().includes(s)
      );
    }
    r.sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      const cmp = av > bv ? 1 : av < bv ? -1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return r;
  }, [threats, sort, filter, q]);

  function toggleSort(key) {
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }
    );
  }

  return (
    <div>
      <div className="section-head">
        <h2>Threat Log</h2>
        <span className="hint">{rows.length} of {threats.length} incidents</span>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
        <div className="fb">
          {FILTERS.map((f) => (
            <button
              key={f}
              className={filter === f ? "active" : ""}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search type or session…"
          style={{
            marginLeft: "auto",
            background: "#050505",
            border: "1px solid #222",
            color: "#ededed",
            padding: "8px 12px",
            fontFamily: "JetBrains Mono",
            fontSize: 11,
            minWidth: 240,
            outline: "none",
          }}
        />
      </div>

      <div className="panel">
        <div className="pbody" style={{ padding: 0 }}>
          {rows.length === 0 ? (
            <div className="empty">
              <div className="glyph">🦇</div>
              {threats.length === 0 ? pick(IDLE_LINES) : "No incidents match the filter."}
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} onClick={() => toggleSort(c.key)}>
                      {c.label}
                      {sort.key === c.key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.request_id} className="row" onClick={() => onSelect(t.request_id)}>
                    <td className="faint mono">{fmtTime(t.timestamp)}</td>
                    <td>{t.threat_type}</td>
                    <td>
                      <span className={`tick ${t.threat_level}`}>{t.threat_level}</span>
                    </td>
                    <td className="mono">{score(t.anomaly_score)}</td>
                    <td className="mono">{score(t.extraction_score)}</td>
                    <td>
                      <span className={`act ${t.action}`}>{t.action}</span>
                    </td>
                    <td className="muted mono">
                      {t.session_id}
                      {(t.session_id || "").startsWith("CTRL-") && (
                        <span className="badge-ctrl" title="Controlled security test — not production traffic">
                          test
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
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
function score(s) {
  return typeof s === "number" ? s.toFixed(2) : "—";
}
