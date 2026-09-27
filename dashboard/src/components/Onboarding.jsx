import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { BatLogo } from "./BatLogo.jsx";

// First-run onboarding wizard. Walks a brand-new developer through the real
// self-serve funnel end to end:
//   1. create a project   -> POST /projects
//   2. register a model    -> POST /models
//   3. generate an API key -> POST /keys   (shown exactly once)
//   4. integrate           -> real SDK + REST snippets using their key
//
// Every step calls the real backend. Nothing here is faked: the project,
// model, and key created during onboarding are the same records the rest of
// the dashboard reads. If the user already has projects/models we let them
// skip ahead so onboarding is never a dead end.

const STEPS = ["Project", "Model", "API Key", "Integrate"];
const ENVS = ["development", "staging", "production"];

export function Onboarding({ onDone }) {
  const [step, setStep] = useState(0);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  // Created records carried across steps.
  const [project, setProject] = useState(null);
  const [model, setModel] = useState(null);
  const [freshKey, setFreshKey] = useState(null);

  // Form state.
  const [pName, setPName] = useState("");
  const [pEnv, setPEnv] = useState("development");
  const [mName, setMName] = useState("");
  const [kName, setKName] = useState("");
  const [copied, setCopied] = useState(false);

  // If the account already has data (e.g. returning here manually), surface it
  // so the wizard picks up where they left off instead of forcing duplicates.
  useEffect(() => {
    (async () => {
      try {
        const projects = (await api.projects()).projects || [];
        if (projects.length) {
          setProject(projects[0]);
          const models = (await api.models(projects[0].project_id)).models || [];
          if (models.length) {
            setModel(models[0]);
            setStep(2);
          } else {
            setStep(1);
          }
        }
      } catch {
        /* not fatal — start from step 0 */
      }
    })();
  }, []);

  async function createProject(e) {
    e.preventDefault();
    if (!pName.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.createProject(pName.trim(), pEnv);
      setProject(r.project || r);
      setStep(1);
    } catch (e2) {
      setErr(String(e2.message));
    } finally {
      setBusy(false);
    }
  }

  async function registerModel(e) {
    e.preventDefault();
    if (!project || !mName.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.registerModel(project.project_id, mName.trim());
      setModel(r.model || r);
      setStep(2);
    } catch (e2) {
      setErr(String(e2.message));
    } finally {
      setBusy(false);
    }
  }

  async function createKey(e) {
    e.preventDefault();
    if (!project || !model) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.createKey(project.project_id, model.model_id, kName.trim() || null);
      setFreshKey(r.api_key); // shown once
      setStep(3);
    } catch (e2) {
      setErr(String(e2.message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card onboard-card">
        <div className="auth-brand">
          <BatLogo />
          <span className="name">BATMAN</span>
        </div>
        <div className="auth-sub">Let's protect your first model</div>

        <ol className="onboard-steps">
          {STEPS.map((s, i) => (
            <li key={s} className={i === step ? "cur" : i < step ? "done" : ""}>
              <span className="n">{i < step ? "✓" : i + 1}</span>
              <span className="l">{s}</span>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <form onSubmit={createProject} className="onboard-form">
            <p className="muted">A project groups the models you protect.</p>
            <input
              className="auth-input"
              placeholder="project name (e.g. Fraud Scoring)"
              value={pName}
              required
              onChange={(e) => setPName(e.target.value)}
            />
            <select className="select" value={pEnv} onChange={(e) => setPEnv(e.target.value)}>
              {ENVS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
            <button className="btn auth-submit" disabled={busy} type="submit">
              {busy ? "…" : "Create project"}
            </button>
          </form>
        )}

        {step === 1 && (
          <form onSubmit={registerModel} className="onboard-form">
            <p className="muted">
              Register the model you want BATMAN to watch, under{" "}
              <strong>{project?.name}</strong>.
            </p>
            <input
              className="auth-input"
              placeholder="model name (e.g. fraud-v1)"
              value={mName}
              required
              onChange={(e) => setMName(e.target.value)}
            />
            <button className="btn auth-submit" disabled={busy} type="submit">
              {busy ? "…" : "Register model"}
            </button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={createKey} className="onboard-form">
            <p className="muted">
              Generate an API key for <strong>{model?.name}</strong>. Your client
              sends this key with every request.
            </p>
            <input
              className="auth-input"
              placeholder="key name (optional)"
              value={kName}
              onChange={(e) => setKName(e.target.value)}
            />
            <button className="btn auth-submit" disabled={busy} type="submit">
              {busy ? "…" : "Generate API key"}
            </button>
          </form>
        )}

        {step === 3 && (
          <div className="onboard-form">
            {freshKey ? (
              <>
                <p className="muted">
                  Copy your key now — it won't be shown again.
                </p>
                <div className="keyreveal-inline">
                  <code className="mono keyval">{freshKey}</code>
                  <button
                    className="btn small"
                    type="button"
                    onClick={() => {
                      navigator.clipboard?.writeText(freshKey);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }}
                  >
                    {copied ? "copied ✓" : "copy"}
                  </button>
                </div>
              </>
            ) : (
              <p className="muted">
                Your key is available on the API Keys page. Use one of the
                integration options below.
              </p>
            )}

            <IntegrationSnippets apiKey={freshKey || "bm_live_xxxxx"} />

            <button className="btn auth-submit" type="button" onClick={onDone}>
              Enter the Batcave
            </button>
          </div>
        )}

        {err && <div className="auth-err">{err}</div>}

        <div className="onboard-foot">
          {step < 3 && (
            <button className="linkbtn" type="button" onClick={onDone}>
              skip for now
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Integration snippets that match the actual batman_ml SDK and gateway REST
// contract. base_url is left as a placeholder the user replaces with their
// deployed BATMAN URL.
function IntegrationSnippets({ apiKey }) {
  const [tab, setTab] = useState("sdk");
  return (
    <div className="integrate-block">
      <div className="mini-tabs">
        <button className={tab === "sdk" ? "active" : ""} onClick={() => setTab("sdk")}>
          Python SDK
        </button>
        <button className={tab === "rest" ? "active" : ""} onClick={() => setTab("rest")}>
          REST
        </button>
      </div>
      {tab === "sdk" ? (
        <pre className="code">{`pip install batman-ml

from batman_ml import protect

protected = protect(
    api_key="${apiKey}",
    base_url="https://your-batman.example",
)
prediction = protected.predict([[/* features */]])`}</pre>
      ) : (
        <pre className="code">{`curl -X POST https://your-batman.example/v1/predict \\
  -H "x-api-key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"inputs": [[/* features */]]}'`}</pre>
      )}
    </div>
  );
}
