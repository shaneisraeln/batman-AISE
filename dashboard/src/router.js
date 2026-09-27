// Minimal hash-based router — no external dependency.
//
// The dashboard is a single-page app served under /app/. We use the URL hash
// so the static landing page can deep-link into specific screens
// (e.g. /app/#/signup, /app/#/login) without any server-side routing.
//
// Routes are simple strings after the "#/": "login", "signup", "onboard",
// "app". Unknown/empty hashes fall back to "app" (the authed default) or
// "login" depending on auth state (decided in App.jsx).

import { useEffect, useState } from "react";

export function currentRoute() {
  const h = window.location.hash || "";
  // "#/signup" -> "signup"; "#/" or "" -> ""
  const m = h.replace(/^#\/?/, "").split(/[/?]/)[0];
  return m || "";
}

export function navigate(route) {
  const next = `#/${route}`;
  if (window.location.hash !== next) {
    window.location.hash = next;
  }
}

// React hook: returns the current route and re-renders on hashchange.
export function useHashRoute() {
  const [route, setRoute] = useState(currentRoute());
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [route, navigate];
}
