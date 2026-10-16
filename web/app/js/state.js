// Practice decisions and patient-journey events layered on top of engine output. Persisted per viewer (demo only).
import { STORAGE_KEY } from "./config.js";

const listeners = new Set();
let decisions = load();
let lastUndo = null;

function load() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; }
}
function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions)); } catch { /* storage unavailable: keep in memory */ }
}
function commit(changes) {
  const before = {};
  for (const id of Object.keys(changes)) before[id] = decisions[id] ? { ...decisions[id] } : undefined;
  lastUndo = before;
  for (const [id, patch] of Object.entries(changes)) decisions[id] = { ...(decisions[id] || {}), ...patch };
  save();
  listeners.forEach((fn) => fn());
}
const event = (id, stage, date, extra = {}) =>
  ({ stage, ...extra, journey: [...(decisions[id]?.journey || []), { stage, date, ...extra }] });

export const store = {
  get: (id) => decisions[id] || {},
  subscribe: (fn) => listeners.add(fn),

  send(items, date) { // items: [{id, channel, variant, text}]
    commit(Object.fromEntries(items.map((i) => [i.id, {
      sent: { channel: i.channel, variant: i.variant, date, text: i.text }, skipped: false, draft: null,
      ...event(i.id, "sent", date, { channel: i.channel }),
    }])));
  },
  /** Journey step: interested | callback | not_now | booked | declined | ldct | result (extra: {result}) */
  step(id, stage, date, extra = {}) { commit({ [id]: event(id, stage, date, extra) }); },
  skip(id, skipped = true) { commit({ [id]: { skipped } }); },
  /** Nurse's change to one invitation in the weekly batch (channel and/or text). Sent with the batch. */
  draft(id, channel, text) { commit({ [id]: { draft: { channel, text }, skipped: false } }); },
  include(id) { commit({ [id]: { override: "ELIGIBLE" } }); },
  exclude(id) { commit({ [id]: { override: "EXCLUDED" } }); },

  /** Live mode: server decisions win for the fields they carry; local-only flags (skip, override) are kept. */
  merge(remote) {
    for (const [id, d] of Object.entries(remote)) decisions[id] = { ...(decisions[id] || {}), ...d };
    save();
  },

  canUndo: () => !!lastUndo,
  undo() {
    if (!lastUndo) return;
    for (const [id, prev] of Object.entries(lastUndo)) prev ? (decisions[id] = prev) : delete decisions[id];
    lastUndo = null;
    save();
    listeners.forEach((fn) => fn());
  },
  reset() { decisions = {}; lastUndo = null; save(); listeners.forEach((fn) => fn()); },
};
