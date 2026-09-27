import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Models section: register a model under a project and point it at an upstream
// ML API (existing-API protection). Upstream credentials are write-only —
// they're encrypted server-side and never returned.
export function Models() {
  const [projects, setProjects] = useState([]);
  const [models, setModels] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState(null);
  const [upstreamFor, setUpstreamFor] = useState(null);

  async function load() {
    try {
      const pr = (await api.projects()).projects || [];
      setProjects(pr);
      if (!projectId && pr.length) setProjectId(pr[0].project_id);
      setModels((await api.models()).models || []);
    } catch (e) {
      setErr(String(e.message));
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function register(e) {
    e.preventDefault();
    if (!projectId || !name.trim()) return;
    try {
      await api.registerModel(projectId, name);
      setName("");
      await load();
    } catch (e2) {
      setErr(String(e2.message));
    }
  }

  return (
    <div>
      <div className="section-head">
        <h2>Protected Models</h2>
        <span className="hint">{models.length} model(s)</span>
      </div>

      <div className="panel" style={{ marginBottom: 22 }}>
        <div className="phead">Register Model</div>
        <div className="pbody">
          {projects.length === 0 ? (
            <div className="muted">Create a project first.</div>
          ) : (
            <form onSubmit={register} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <select className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <input
                className="auth-input"
                style={{ flex: 1, minWidth: 180, margin: 0 }}
                placeholder="model name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <button className="btn" type="submit">Register</button>
            </form>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="pbody" style={{ padding: 0 }}>
          {models.length === 0 ? (
            <div className="empty"><div className="glyph">🦇</div>No models registered.</div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Model ID</th>
                  <th>Status</th>
                  <th>Upstream</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.model_id}>
                    <td>{m.name}</td>
                    <td className="mono faint">{m.model_id}</td>
                    <td><span className="act ALLOW">{m.status}</span></td>
                    <td>
                      <button className="btn small" onClick={() => setUpstreamFor(m)}>
                        Configure
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {upstreamFor && (
        <UpstreamModal model={upstreamFor} onClose={() => setUpstreamFor(null)} onSaved={load} />
      )}
      {err && <div className="auth-err" style={{ marginTop: 12 }}>{err}</div>}
    </div>
  );
}

function UpstreamModal({ model, onClose, onSaved }) {
  const [url, setUrl] = useState("");
  const [authType, setAuthType] = useState("none");
  const [secret, setSecret] = useState("");
  const [headerName, setHeaderName] = useState("X-API-Key");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api.setUpstream(model.model_id, {
        url,
        auth_type: authType,
        auth_secret: authType === "none" ? null : secret,
        auth_header_name: authType === "header" ? headerName : null,
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(String(e.message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Upstream for “{model.name}”</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Point BATMAN at your deployed model's prediction endpoint. Credentials are
          encrypted at rest and never shown again.
        </p>
        <input className="auth-input" placeholder="https://your-api.example/predict"
               value={url} onChange={(e) => setUrl(e.target.value)} />
        <select className="select" style={{ width: "100%", marginBottom: 10 }}
                value={authType} onChange={(e) => setAuthType(e.target.value)}>
          <option value="none">no upstream auth</option>
          <option value="bearer">Bearer token</option>
          <option value="header">custom header</option>
        </select>
        {authType === "header" && (
          <input className="auth-input" placeholder="header name" value={headerName}
                 onChange={(e) => setHeaderName(e.target.value)} />
        )}
        {authType !== "none" && (
          <input className="auth-input" type="password" placeholder="upstream secret (write-only)"
                 value={secret} onChange={(e) => setSecret(e.target.value)} />
        )}
        {err && <div className="auth-err">{err}</div>}
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <button className="btn" disabled={busy || !url} onClick={save}>
            {busy ? "…" : "Save"}
          </button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
