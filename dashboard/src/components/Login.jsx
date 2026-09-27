import React, { useState } from "react";
import { api } from "../api.js";
import { navigate } from "../router.js";
import { BatLogo } from "./BatLogo.jsx";

export function Login({ onAuthed, initialMode = "login" }) {
  const [mode, setMode] = useState(initialMode === "signup" ? "signup" : "login"); // login | signup
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (mode === "signup") {
        await api.signup(email, password, name || null);
        // Fresh accounts go straight into onboarding.
        onAuthed({ isNew: true });
        return;
      }
      await api.login(email, password);
      onAuthed({ isNew: false });
      return;
    } catch (e2) {
      setErr(
        mode === "signup"
          ? "Could not sign up. Email may already be registered, or password too short (min 8)."
          : "Invalid credentials."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <BatLogo />
          <span className="name">BATMAN</span>
        </div>
        <div className="auth-sub">Runtime security for ML inference</div>

        <div className="auth-tabs">
          <button
            className={mode === "login" ? "active" : ""}
            onClick={() => {
              setMode("login");
              navigate("login");
            }}
          >
            Sign In
          </button>
          <button
            className={mode === "signup" ? "active" : ""}
            onClick={() => {
              setMode("signup");
              navigate("signup");
            }}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={submit}>
          {mode === "signup" && (
            <input
              className="auth-input"
              placeholder="name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
          <input
            className="auth-input"
            type="email"
            placeholder="email"
            value={email}
            required
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="auth-input"
            type="password"
            placeholder="password (min 8 chars)"
            value={password}
            required
            onChange={(e) => setPassword(e.target.value)}
          />
          {err && <div className="auth-err">{err}</div>}
          <button className="btn auth-submit" disabled={busy} type="submit">
            {busy ? "…" : mode === "signup" ? "Create account" : "Enter the Batcave"}
          </button>
        </form>
        <div className="auth-foot">Your key. Your model. Watched.</div>
      </div>
    </div>
  );
}
