// Vitest global setup for the dashboard test suite.
//
// - registers jest-dom matchers (toBeInTheDocument, etc.)
// - resets localStorage, fetch mock, and the URL hash between tests so each
//   test starts from a clean, deterministic state
// - provides ResizeObserver + a non-zero layout box so recharts'
//   ResponsiveContainer can render inside jsdom (it measures its parent)

import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// recharts ResponsiveContainer relies on ResizeObserver + element dimensions.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;

// jsdom returns 0 for layout; give charts a real box so they render.
Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
  configurable: true,
  value: 800,
});
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
  configurable: true,
  value: 400,
});

beforeEach(() => {
  localStorage.clear();
  // Start each test at the app root hash.
  window.location.hash = "";
  // A fresh fetch mock per test; individual tests define responses.
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
