import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import { Overview } from "./components/Overview.jsx";
import { Threats } from "./components/Threats.jsx";
import { ThreatDetail } from "./components/ThreatDetail.jsx";
import { Monitoring } from "./components/Monitoring.jsx";

const TABS = ["Overview", "Threats", "Monitoring"];

export default function App() {
  const [tab, setTab] = useState("Overview");
  const [metrics, setMetrics] = useState({});
  const [threats, setThreats] = useState([]);
  const [health, setHealth] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [m, t, h] = await Promise.all([
        api.metrics(),
        api.threats(200),
        api.health(),
      ]);
      setMetrics(m);
      setThreats(t.threats || []);
      setHealth(h);
      setError(null);
    } catch (e) {
      setError("Gateway unreachable. Start it: uvicorn batman.gateway.app:app");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="app">
      <div className="header">
        <div className="brand">
          <span className="bat">🦇</span>
          <h1>BATMAN</h1>
          <span className="muted" style={{ fontSize: 12 }}>
            Behavioral AI Threat Monitoring
          </span>
        </div>
        <div className="health">
          {health ? (
            <>
              <div>
                <span className="dot ok" />
                gateway online · mode {health.mode}
              </div>
              <div>
                detector {health.detector_ready ? "ready" : "not trained"} · llm{" "}
                {health.llm_provider} · rag {health.rag_backend}
              </div>
            </>
          ) : (
            <div>
              <span className="dot off" />
              {error || "connecting…"}
            </div>
          )}
        </div>
      </div>

      {!selected && (
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t}
              className={`tab ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {selected ? (
        <ThreatDetail requestId={selected} onBack={() => setSelected(null)} />
      ) : tab === "Overview" ? (
        <Overview metrics={metrics} />
      ) : tab === "Threats" ? (
        <Threats threats={threats} onSelect={setSelected} />
      ) : (
        <Monitoring metrics={metrics} threats={threats} />
      )}
    </div>
  );
}
