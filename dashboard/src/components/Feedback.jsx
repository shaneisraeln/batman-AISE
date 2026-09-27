import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Analyst Feedback log — the record of verdicts analysts have submitted on
// detections, tenant-scoped. Data comes from GET /v1/feedback (Bearer,
// server-side filtered to the caller's own projects). Nothing is fabricated;
// an empty log renders an honest empty state.

// Feedback labels get their own colour scale (see .fblabel in styles.css).
const KNOWN_LABELS = [
  "TRUE_POSITIVE",
  "FALSE_POSITIVE",
  "TRUE_NEGATIVE",
  "FALSE_NEGATIVE",
  "UNCERTAIN",
];

export function Feedback({ onSelect }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.listFeedback(200);
      setRows(r.feedback || []);
    } catch (e) {
      setErr(String(e.message));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  // Small live summary of verdict distribution.
  const counts = {};
  for (const r of rows) counts[r.label] = (counts[r.label] || 0) + 1;

  return (
    <div>
      <div className="section-head">
        <h2>Analyst Feedback</h2>
        <span className="hint">{rows.length} verdict(s) · tenant-scoped</span>
      </div>

      {rows.length > 0 && (
        <div className="fb-summary">
          {Object.entries(counts).map(([label, c]) => (
            <span key={label} className={`fblabel ${KNOWN_LABELS.includes(label) ? label : ""}`}>
              {label} · {c}
            </span>
          ))}
        </div>
      )}

      <div className="panel">
        <div className="pbody" style={{ padding: 0 }}>
          {loading ? (
            <div className="empty">loading…</div>
          ) : rows.length === 0 ? (
            <div className="empty">
              <div className="glyph">🦇</div>
              No feedback yet. Open a threat and record a verdict — it will show
              up here to inform future evaluation.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Verdict</th>
                  <th>Threat</th>
                  <th>Note</th>
                  <th>Request</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={`${r.request_id}-${i}`}
                    className={onSelect ? "row" : ""}
                    onClick={() => onSelect && onSelect(r.request_id)}
                  >
                    <td className="faint mono" style={{ width: 150 }}>
                      {fmt(r.created_at)}
                    </td>
                    <td>
                      <span className={`fblabel ${KNOWN_LABELS.includes(r.label) ? r.label : ""}`}>
                        {r.label}
                      </span>
                    </td>
                    <td className="muted">{r.threat_type || "—"}</td>
                    <td className="muted">{r.analyst_note || <span className="faint">—</span>}</td>
                    <td className="mono faint">{r.request_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      {err && <div className="auth-err" style={{ marginTop: 12 }}>{err}</div>}
    </div>
  );
}

function fmt(ts) {
  try {
    return new Date(ts).toLocaleString([], { hour12: false });
  } catch {
    return "—";
  }
}
