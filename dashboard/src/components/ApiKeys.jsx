import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// API Keys section. New keys are shown exactly once, then only metadata remains.
export function ApiKeys() {
  const [keys, setKeys] = useState([]);
  const [projects, setProjects] = useState([]);
  const [models, setModels] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [name, setName] = useState("");
  const [freshKey, setFreshKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState(null);

  async function load() {
    try {
      setKeys((await api.keys()).api_keys || []);
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

  const projectModels = models.filter((m) => m.project_id === projectId);

  async function create(e) {
    e.preventDefault();
    if (!projectId || !modelId) return;
    try {
      const r = await api.createKey(projectId, modelId, name || null);
      setFreshKey(r.api_key); // shown once
      setName("");
      await load();
    } catch (e2) {
      setErr(String(e2.message));
    }
  }

  async function revoke(key_id) {
    try {
      await api.revokeKey(key_id);
      await load();
    } catch (e) {
      setErr(String(e.message));
    }
  }

  return (
    <div>
      <div className="section-head">
        <h2>API Keys</h2>
        <span className="hint">{keys.length} key(s)</span>
      </div>

      {freshKey && (
        <div className="panel keyreveal" style={{ marginBottom: 22 }}>
          <div className="phead">New key — copy it now, it won't be shown again</div>
          <div className="pbody" style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <code className="mono keyval">{freshKey}</code>
            <button
              className="btn small"
              onClick={() => {
                navigator.clipboard?.writeText(freshKey);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
            >
              {copied ? "copied ✓" : "copy"}
            </button>
            <button className="btn small" onClick={() => setFreshKey(null)}>dismiss</button>
          </div>
        </div>
      )}

      <div className="panel" style={{ marginBottom: 22 }}>
        <div className="phead">Generate Key</div>
        <div className="pbody">
          {projects.length === 0 || models.length === 0 ? (
            <div className="muted">Create a project and register a model first.</div>
          ) : (
            <form onSubmit={create} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <select className="select" value={projectId}
                      onChange={(e) => { setProjectId(e.target.value); setModelId(""); }}>
                {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
              </select>
              <select className="select" value={modelId} onChange={(e) => setModelId(e.target.value)}>
                <option value="">select model…</option>
                {projectModels.map((m) => <option key={m.model_id} value={m.model_id}>{m.name}</option>)}
              </select>
              <input className="auth-input" style={{ margin: 0, minWidth: 150 }}
                     placeholder="key name (optional)" value={name}
                     onChange={(e) => setName(e.target.value)} />
              <button className="btn" type="submit" disabled={!modelId}>Generate</button>
            </form>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="pbody" style={{ padding: 0 }}>
          {keys.length === 0 ? (
            <div className="empty"><div className="glyph">🦇</div>No keys yet.</div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th><th>Key ID</th><th>Model</th><th>Status</th>
                  <th>Created</th><th>Last used</th><th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.key_id}>
                    <td>{k.name || <span className="faint">—</span>}</td>
                    <td className="mono faint">{k.key_id}</td>
                    <td className="mono faint">{k.model_id}</td>
                    <td>
                      <span className={`act ${k.status === "active" ? "ALLOW" : "BLOCK"}`}>
                        {k.status}
                      </span>
                    </td>
                    <td className="faint mono">{fmt(k.created_at)}</td>
                    <td className="faint mono">{k.last_used_at ? fmt(k.last_used_at) : "never"}</td>
                    <td>
                      {k.status === "active" && (
                        <button className="btn small danger" onClick={() => revoke(k.key_id)}>
                          revoke
                        </button>
                      )}
                    </td>
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
