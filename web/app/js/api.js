// Thin client for the backend. Every call throws on HTTP error; callers decide what to show.
import { API_BASE } from "./config.js";

async function call(path, body) {
  const r = await fetch(API_BASE + path, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : undefined);
  if (r.status === 401 && path !== "/api/health") location.href = "/login?next=/app/"; // session expired: sign in again
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
  mark: (id, field, value) => call("/api/mark", { id, field, value }),
  fhirSync: () => call("/api/fhir/sync", {}),
  recipient: () => call("/api/recipient"),
  /** {ok:true, ...recipient} or {ok:false, error} with the server's Czech message (validation). */
  setRecipient: async (phone, email) => {
    const r = await fetch(API_BASE + "/api/recipient", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone, email }) });
    const j = await r.json().catch(() => ({}));
    return r.ok ? { ok: true, ...j } : { ok: false, error: j.detail || String(r.status) };
  },
  patient: (id) => call(`/api/patient/${encodeURIComponent(id)}`),
};
