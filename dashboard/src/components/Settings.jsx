import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export function Settings({ health, onLogout }) {
  const [me, setMe] = useState(null);
  useEffect(() => {
    api.me().then(setMe).catch(() => {});
  }, []);

  return (
    <div>
      <div className="section-head">
        <h2>Settings</h2>
      </div>

      <div className="detail-grid">
        <div className="panel">
          <div className="phead">Account</div>
          <div className="pbody">
            <div className="kv"><span className="k">Email</span><span className="val">{me?.email || "…"}</span></div>
            <div className="kv"><span className="k">Name</span><span className="val">{me?.display_name || "—"}</span></div>
            <div className="kv"><span className="k">User ID</span><span className="val mono faint">{me?.user_id || "…"}</span></div>
            <div style={{ marginTop: 14 }}>
              <button className="btn danger" onClick={onLogout}>Sign out</button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="phead">Service Status</div>
          <div className="pbody">
            <div className="kv"><span className="k">Gateway</span><span className="val">{health?.status || "…"}</span></div>
            <div className="kv"><span className="k">Mode</span><span className="val">{health?.mode || "…"}</span></div>
            <div className="kv"><span className="k">Detector</span><span className="val">{health?.detector_ready ? "armed" : "cold"}</span></div>
            <div className="kv"><span className="k">LLM</span><span className="val">{health?.llm_provider || "…"}</span></div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 22 }}>
        <div className="phead">Integration — Quickstart</div>
        <div className="pbody">
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
            Install the lightweight client (httpx-only, no ML deps) and route
            inference through BATMAN.
          </p>
          <pre className="code-block">{`pip install batman-ml`}</pre>
          <pre className="code-block">{`from batman_ml import protect

protected = protect(
    api_key="bm_live_xxxxx",      # from the API Keys tab
    base_url="${window.location.origin}",
)
prediction = protected.predict(X)`}</pre>
          <p className="muted" style={{ fontSize: 12 }}>
            Need the full security decision (action, threat type, request id)?
            Use the client directly:
          </p>
          <pre className="code-block">{`from batman_ml import BatmanClient

client = BatmanClient(
    api_key="bm_live_xxxxx",
    base_url="${window.location.origin}",
)
result = client.predict(X)
print(result.action, result.threat_type, result.request_id)
print(result.prediction)`}</pre>
          <p className="muted" style={{ fontSize: 12 }}>
            Or call the REST data plane directly:
          </p>
          <pre className="code-block">{`curl -X POST ${window.location.origin}/v1/predict \\
  -H "x-api-key: bm_live_xxxxx" \\
  -H "Content-Type: application/json" \\
  -d '{"inputs": [[/* features */]]}'`}</pre>
        </div>
      </div>
    </div>
  );
}
