// Practice decisions and patient-journey events layered on top of engine output. Persisted per viewer (demo only).
import { STORAGE_KEY } from "./config.js";
import { next, refusals } from "./fsm.js";

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

/** Local (no backend) transition through the journey state machine; a disallowed event is only recorded. */
function transition(id, ev, date, extra = {}) {
  const d = decisions[id] || {};
  const target = next(d.stage, ev, refusals(d.journey));
  if (!target) return { journey: [...(d.journey || []), { stage: null, event: ev, date, ignored: true, ...extra }] };
  if (ev === "declined" || ev === "opt_out") extra = { intent: ev, ...extra };
  const patch = event(id, target, date, { event: ev, ...extra });
  return target === "new" ? { ...patch, stage: undefined } : patch; // re-included: back to the start
}

export const store = {
  get: (id) => decisions[id] || {},
  subscribe: (fn) => listeners.add(fn),

  send(items, date) { // items: [{id, channel, variant, text}]
    commit(Object.fromEntries(items.filter((i) => next(decisions[i.id]?.stage, "send")).map((i) => [i.id, {
      sent: { channel: i.channel, variant: i.variant, date, text: i.text }, skipped: false, draft: null,
      ...transition(i.id, "send", date, { channel: i.channel }),
    }])));
  },
  /** Journey event (see content/journey.json): interested | callback | not_now | booked | no_show | declined | ldct | result … */
  step(id, ev, date, extra = {}) { commit({ [id]: transition(id, ev, date, extra) }); },
  skip(id, skipped = true) { commit({ [id]: { skipped } }); },
  /** Nurse's change to one invitation in the weekly batch (channel and/or text). Sent with the batch. */
  draft(id, channel, text) { commit({ [id]: { draft: { channel, text }, skipped: false } }); },
  include(id) { commit({ [id]: { override: "ELIGIBLE" } }); },
  exclude(id) { commit({ [id]: { override: "EXCLUDED" } }); },
  /** Practice decision that is not a journey event: skipped, draft, override, resultAck. */
  mark(id, field, value) { commit({ [id]: { [field]: value } }); },

  /** Live mode: the server is the source of truth for every patient (decisions are stored there too). */
  merge(remote) {
    decisions = JSON.parse(JSON.stringify(remote));
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
