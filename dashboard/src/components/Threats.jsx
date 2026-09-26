import React from "react";

export function Threats({ threats, onSelect }) {
  if (!threats || threats.length === 0) {
    return (
      <div className="panel">
        <h2>Threats</h2>
        <div className="empty">
          No threats recorded yet. Start the gateway and run the demo simulator.
        </div>
      </div>
    );
  }
  return (
    <div className="panel">
      <h2>Detected Threats ({threats.length})</h2>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Threat Type</th>
            <th>Level</th>
            <th>Anomaly</th>
            <th>Extraction</th>
            <th>Action</th>
            <th>Session</th>
          </tr>
        </thead>
        <tbody>
          {threats.map((t) => (
            <tr
              key={t.request_id}
              className="clickable"
              onClick={() => onSelect(t.request_id)}
            >
              <td className="mono">{fmtTime(t.timestamp)}</td>
              <td>{t.threat_type}</td>
              <td>{t.threat_level}</td>
              <td>{fmtScore(t.anomaly_score)}</td>
              <td>{fmtScore(t.extraction_score)}</td>
              <td>
                <span className={`badge ${t.action}`}>{t.action}</span>
              </td>
              <td className="mono muted">{t.session_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts;
  }
}
function fmtScore(s) {
  return typeof s === "number" ? s.toFixed(2) : "—";
}
