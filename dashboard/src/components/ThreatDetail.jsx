import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const LABELS = [
  "TRUE_POSITIVE",
  "FALSE_POSITIVE",
  "TRUE_NEGATIVE",
  "FALSE_NEGATIVE",
  "UNCERTAIN",
];

export function ThreatDetail({ requestId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [submitting, setSubmitting] = useState(null);
  const [submitted, setSubmitted] = useState(null);

  useEffect(() => {
    api.threatDetail(requestId).then(setDetail).catch((e) => setErr(String(e)));
  }, [requestId]);

  async function submitFeedback(label) {
    setSubmitting(label);
    try {
      await api.feedback(requestId, label, "Submitted from dashboard");
      setSubmitted(label);
      const d = await api.threatDetail(requestId);
      setDetail(d);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(null);
    }
  }

  if (err) return <div className="panel"><span className="back" onClick={onBack}>← Back</span><div className="empty">{err}</div></div>;
  if (!detail) return <div className="panel"><div className="empty">Loading…</div></div>;

  const feats = detail.features || {};
  const existingFeedback = detail.feedback || [];

  return (
    <div>
      <span className="back" onClick={onBack}>← Back to threats</span>
      <div className="detail-grid">
        <div className="panel">
          <h2>Decision</h2>
          <div className="kv"><span className="k">Request ID</span><span className="mono">{detail.request_id}</span></div>
          <div className="kv"><span className="k">Threat Type</span>{detail.threat_type}</div>
          <div className="kv"><span className="k">Threat Level</span>{detail.threat_level}</div>
          <div className="kv"><span className="k">Action</span><span className={`badge ${detail.action}`}>{detail.action}</span></div>
          <div className="kv"><span className="k">Anomaly Score</span>{fmt(detail.anomaly_score)}</div>
          <div className="kv"><span className="k">Extraction Score</span>{fmt(detail.extraction_score)}</div>
          <div className="kv"><span className="k">Latency (ms)</span>{fmt(detail.latency_ms)}</div>
          <div className="kv"><span className="k">Detector</span><span className="mono">{detail.detector_version}</span></div>
          <div className="kv"><span className="k">Reason</span><span className="muted">{detail.reason}</span></div>
        </div>

        <div className="panel">
          <h2>Behavioral Features</h2>
          {Object.entries(feats).map(([k, v]) => (
            <div className="kv" key={k}>
              <span className="k">{k}</span>
              {typeof v === "number" ? v.toFixed(3) : String(v)}
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Analyst Feedback</h2>
        {submitted && <div className="muted">Recorded: {submitted}</div>}
        {existingFeedback.length > 0 && (
          <div className="muted" style={{ marginBottom: 8 }}>
            Prior labels: {existingFeedback.map((f) => f.label).join(", ")}
          </div>
        )}
        <div className="fb-buttons">
          {LABELS.map((l) => (
            <button
              key={l}
              className={`btn ${submitted === l ? "active" : ""}`}
              disabled={!!submitting}
              onClick={() => submitFeedback(l)}
            >
              {submitting === l ? "…" : l}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function fmt(v) {
  return typeof v === "number" ? v.toFixed(3) : v ?? "—";
}
