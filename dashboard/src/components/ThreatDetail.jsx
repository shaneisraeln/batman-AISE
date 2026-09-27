import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const LABELS = [
  "TRUE_POSITIVE",
  "FALSE_POSITIVE",
  "TRUE_NEGATIVE",
  "FALSE_NEGATIVE",
  "UNCERTAIN",
];

// Features shown with a normalized bar (rough scale for quick visual scan).
const FEATURE_SCALE = {
  request_rate: 240,
  session_request_count: 150,
  input_norm: 120,
  query_similarity: 1,
  unique_input_ratio: 1,
  duplicate_ratio: 1,
  inter_request_time: 10,
  previous_anomaly_count: 50,
};

export function ThreatDetail({ requestId, onBack }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);
  const [done, setDone] = useState(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    api.threatDetail(requestId).then(setD).catch((e) => setErr(String(e)));
  }, [requestId]);

  async function submit(label) {
    setBusy(label);
    try {
      await api.feedback(requestId, label, note || "logged from console");
      setDone(label);
      setD(await api.threatDetail(requestId));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  if (err)
    return (
      <div>
        <span className="back" onClick={onBack}>← return to watch</span>
        <div className="empty">{err}</div>
      </div>
    );
  if (!d) return <div className="empty">decrypting…</div>;

  const feats = d.features || {};
  const fb = d.feedback || [];
  const explanation = d.explanation; // present on threats.detail if stored

  return (
    <div>
      <span className="back" onClick={onBack}>← return to watch</span>

      <div className="detail-grid">
        <div className="panel">
          <div className="phead">Decision</div>
          <div className="pbody">
            <Row k="Request" v={<span className="mono faint">{d.request_id}</span>} />
            <Row k="Threat" v={d.threat_type} />
            <Row k="Level" v={<span className={`tick ${d.threat_level}`}>{d.threat_level}</span>} />
            <Row k="Action" v={<span className={`act ${d.action}`}>{d.action}</span>} />
            <Row k="Anomaly Score" v={num(d.anomaly_score)} />
            <Row k="Extraction Score" v={num(d.extraction_score)} />
            <Row k="Latency" v={`${num(d.latency_ms)} ms`} />
            <Row k="Detector" v={<span className="mono">{d.detector_version}</span>} />
            <Row k="Session" v={<span className="mono">{d.session_id}</span>} />
            <Row k="Rationale" v={<span className="muted">{d.reason || "—"}</span>} />
          </div>
        </div>

        <div className="panel">
          <div className="phead">Behavioral Features</div>
          <div className="pbody">
            {Object.entries(feats).map(([k, v]) => {
              const scale = FEATURE_SCALE[k];
              const pct =
                typeof v === "number" && scale
                  ? Math.min(100, (Math.abs(v) / scale) * 100)
                  : null;
              return (
                <div className="feature-bar" key={k}>
                  <span className="fname">{k}</span>
                  <span className="track">
                    {pct !== null && <span className="fill" style={{ width: `${pct}%` }} />}
                  </span>
                  <span className="fval">
                    {typeof v === "number" ? v.toFixed(2) : String(v)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {explanation && (
        <div className="panel full" style={{ marginTop: 22 }}>
          <div className="phead">Investigation — LLM + RAG</div>
          <div className="pbody">
            <div className="explain">
              <div className="meta">
                grounded analysis {explanation.llm_available ? "· live model" : "· deterministic"}
              </div>
              {explanation.summary}
            </div>
            {explanation.evidence?.length > 0 && (
              <ul className="evlist" style={{ marginTop: 16 }}>
                {explanation.evidence.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <div className="panel full" style={{ marginTop: 22 }}>
        <div className="phead">Analyst Verdict</div>
        <div className="pbody">
          {fb.length > 0 && (
            <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>
              prior: {fb.map((f) => f.label).join(" · ")}
            </div>
          )}
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="note (optional)…"
            style={{
              width: "100%",
              background: "#050505",
              border: "1px solid #222",
              color: "#ededed",
              padding: "9px 12px",
              fontFamily: "JetBrains Mono",
              fontSize: 11,
              outline: "none",
              marginBottom: 12,
            }}
          />
          <div className="fb">
            {LABELS.map((l) => (
              <button
                key={l}
                className={done === l ? "active" : ""}
                disabled={!!busy}
                onClick={() => submit(l)}
              >
                {busy === l ? "…" : l}
              </button>
            ))}
          </div>
          {done && (
            <div style={{ marginTop: 12, color: "#f2c14e", fontSize: 11 }}>
              recorded — {done}. justice served.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span className="val">{v}</span>
    </div>
  );
}
function num(v) {
  return typeof v === "number" ? v.toFixed(3) : "—";
}
