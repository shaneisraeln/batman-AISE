import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const ENVS = ["development", "staging", "production"];

export function Projects() {
  const [projects, setProjects] = useState([]);
  const [name, setName] = useState("");
  const [env, setEnv] = useState("development");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function load() {
    try {
      setProjects((await api.projects()).projects || []);
    } catch (e) {
      setErr(String(e.message));
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function create(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createProject(name, env);
      setName("");
      await load();
    } catch (e2) {
      setErr(String(e2.message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="section-head">
        <h2>Projects</h2>
        <span className="hint">{projects.length} project(s)</span>
      </div>

      <div className="panel" style={{ marginBottom: 22 }}>
        <div className="phead">New Project</div>
        <div className="pbody">
          <form onSubmit={create} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              className="auth-input"
              style={{ flex: 1, minWidth: 200, margin: 0 }}
              placeholder="project name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <select className="select" value={env} onChange={(e) => setEnv(e.target.value)}>
              {ENVS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
            <button className="btn" disabled={busy} type="submit">
              {busy ? "…" : "Create"}
            </button>
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="pbody" style={{ padding: 0 }}>
          {projects.length === 0 ? (
            <div className="empty">
              <div className="glyph">🦇</div>No projects yet. Create one to begin.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Environment</th>
                  <th>Project ID</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.project_id}>
                    <td>{p.name}</td>
                    <td>
                      <span className={`env-badge ${p.environment}`}>{p.environment}</span>
                    </td>
                    <td className="mono faint">{p.project_id}</td>
                    <td className="faint mono">{fmt(p.created_at)}</td>
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
