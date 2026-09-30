import React, { useEffect, useState, useCallback, useRef } from "react";
import { api, isAuthed } from "./api.js";
import { useHashRoute, navigate } from "./router.js";
import { Overview } from "./components/Overview.jsx";
import { Threats } from "./components/Threats.jsx";
import { ThreatDetail } from "./components/ThreatDetail.jsx";
import { Monitoring } from "./components/Monitoring.jsx";
import { Analytics } from "./components/Analytics.jsx";
import { Feedback } from "./components/Feedback.jsx";
import { Projects } from "./components/Projects.jsx";
import { Models } from "./components/Models.jsx";
import { ApiKeys } from "./components/ApiKeys.jsx";
import { Settings } from "./components/Settings.jsx";
import { Login } from "./components/Login.jsx";
import { Onboarding } from "./components/Onboarding.jsx";
import { BatLogo } from "./components/BatLogo.jsx";
import { WATCH_QUOTES, pick, armSignalEgg } from "./components/eggs.js";

const NAV = [
  { group: "Monitor", items: ["Overview", "Threats", "Monitoring", "Analytics"] },
  { group: "Review", items: ["Feedback"] },
  { group: "Manage", items: ["Projects", "Models", "API Keys"] },
  { group: "Account", items: ["Settings"] },
];

export default function App() {
  const [authed, setAuthed] = useState(isAuthed());
  const [route] = useHashRoute();
  const [view, setView] = useState("Overview");
  const [metrics, setMetrics] = useState({});
  const [threats, setThreats] = useState([]);
  const [health, setHealth] = useState(null);
  const [selected, setSelected] = useState(null);
  const [online, setOnline] = useState(true);
  const [signal, setSignal] = useState(false);
  const quote = useRef(pick(WATCH_QUOTES));

  const refresh = useCallback(async () => {
    if (!isAuthed()) return;
    try {
      const [m, t, h] = await Promise.all([api.metrics(), api.threats(300), api.health()]);
      setMetrics(m);
      setThreats(t.threats || []);
      setHealth(h);
      setOnline(true);
    } catch (e) {
      if (String(e.message) === "unauthorized") {
        setAuthed(false);
        return;
      }
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [authed, refresh]);

  useEffect(
    () =>
      armSignalEgg(() => {
        setSignal(true);
        setTimeout(() => setSignal(false), 1600);
      }),
    []
  );

  // ---- routing / auth gate ----
  // Unauthenticated: only login/signup screens are reachable. A landing-page
  // deep link (#/signup) opens the sign-up tab; anything else defaults to login.
  if (!authed) {
    const initialMode = route === "signup" ? "signup" : "login";
    return (
      <Login
        initialMode={initialMode}
        onAuthed={async ({ isNew }) => {
          setAuthed(true);
          // Fresh signups always onboard. A returning user who never finished
          // setup (no project yet) is routed into onboarding too, so nobody
          // lands on an empty dashboard. Existing users go straight to the app.
          let dest = "app";
          if (isNew) {
            dest = "onboard";
          } else {
            try {
              const { projects } = await api.projects();
              if (!projects || projects.length === 0) dest = "onboard";
            } catch {
              /* on any error, fall back to the dashboard */
            }
          }
          navigate(dest);
        }}
      />
    );
  }

  // Authenticated first-run onboarding wizard.
  if (route === "onboard") {
    return <Onboarding onDone={() => navigate("app")} />;
  }

  function logout() {
    api.logout();
    setAuthed(false);
    setView("Overview");
    navigate("login");
  }

  return (
    <div className="shell">
      {signal && <SignalFlash />}
      <aside className="sidebar">
        <a className="mark" href="/" title="Back to batman.site">
          <BatLogo />
          <span className="name">BATMAN</span>
        </a>
        <nav className="nav">
          {NAV.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-group-label">{g.group}</div>
              {g.items.map((n) => (
                <button
                  key={n}
                  className={view === n && !selected ? "active" : ""}
                  onClick={() => {
                    setSelected(null);
                    setView(n);
                  }}
                >
                  {n}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="foot">
          <div>BEHAVIORAL AI</div>
          <div>THREAT MONITORING</div>
          <div style={{ marginTop: 10 }} className="tagline">
            “{quote.current}”
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="title">
            {selected ? "Incident" : view}
            <span className="sub">{selected ? "// forensic detail" : "// gotham watch"}</span>
          </div>
          <div className="status-line">
            <span className="item">
              <span className={`dot ${online ? "on pulse" : "off"}`} />
              <span className="k">{online ? "online" : "offline"}</span>
            </span>
            {health && (
              <>
                <span className="item"><span className="k">mode</span><span className="v">{health.mode}</span></span>
                <span className="item"><span className="k">detector</span><span className="v">{health.detector_ready ? "armed" : "cold"}</span></span>
                <span className="item"><span className="k">llm</span><span className="v">{health.llm_provider}</span></span>
              </>
            )}
          </div>
        </header>

        <div className="content">{renderView()}</div>
      </main>
    </div>
  );

  function renderView() {
    if (selected) return <ThreatDetail requestId={selected} onBack={() => setSelected(null)} />;
    switch (view) {
      case "Overview":
        return <Overview metrics={metrics} threats={threats} onSelect={setSelected} />;
      case "Threats":
        return <Threats threats={threats} onSelect={setSelected} />;
      case "Monitoring":
        return <Monitoring metrics={metrics} threats={threats} />;
      case "Analytics":
        return <Analytics metrics={metrics} threats={threats} />;
      case "Feedback":
        return <Feedback onSelect={setSelected} />;
      case "Projects":
        return <Projects />;
      case "Models":
        return <Models />;
      case "API Keys":
        return <ApiKeys />;
      case "Settings":
        return <Settings health={health} onLogout={logout} />;
      default:
        return <Overview metrics={metrics} threats={threats} onSelect={setSelected} />;
    }
  }
}

function SignalFlash() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        pointerEvents: "none",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(circle at 50% 45%, rgba(242,193,78,0.12), transparent 45%)",
        animation: "rise 0.3s ease",
      }}
    >
      <span style={{ position: "absolute", width: 220, opacity: 0.9 }}>
        <BatLogo />
      </span>
    </div>
  );
}
