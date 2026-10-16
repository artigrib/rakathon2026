// Thin client for the backend. Every call throws on HTTP error; callers decide what to show.
import { API_BASE } from "./config.js";

async function call(path, body) {
  const r = await fetch(API_BASE + path, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : undefined);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const api = {
  /** Resolves to {ok, mode} when a backend is reachable, otherwise null. */
  health: () => call("/api/health").catch(() => null),
  state: () => call("/api/state"),
  send: (items, date) => call("/api/send", { items, date }),
  step: (body) => call("/api/step", body),
  reset: () => call("/api/reset", {}),
  tick: (days = 1) => call("/api/tick", { days }),
  patient: (id) => call(`/api/patient/${encodeURIComponent(id)}`),
};
