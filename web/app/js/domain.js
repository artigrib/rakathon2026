// What the practice has to do about each patient. Pure functions over engine output + recorded decisions.
import { JOURNEY, LOST, RESULTS } from "./config.js";
import { store } from "./state.js";
import { isFinal, sectionOf } from "./fsm.js";

// Demo/real "today" for rules that depend on time (set by the app on every render).
let CLOCK = null;
export const setClock = (c) => { CLOCK = c; };

const effectiveStatus = (p, d) => (d.override === "ELIGIBLE" ? "ELIGIBLE" : p.status);

/** Current journey stage; a patient who replied "interested" in the source data starts at "interested". */
export function stageOf(p) {
  const d = store.get(p.id);
  if (d.override === "EXCLUDED") return "excluded";
  if (d.stage) return d.stage;
  return effectiveStatus(p, d) === "ELIGIBLE" && p.next === "GP_REFERRAL" ? "interested" : null;
}

/** Work-queue section for the patient, or null when nothing needs doing right now. */
export function taskOf(p) {
  const d = store.get(p.id);
  if (d.override === "EXCLUDED") return null;
  const stage = stageOf(p);
  if (stage === "result") { // repeat screening: back in the invite batch once the next LDCT is due
    const due = rescreenDue(p);
    return due && CLOCK && due <= CLOCK ? "invite" : null;
  }
  if (stage) { // section comes from the state machine; "waiting" is the system's work, not a task
    const s = sectionOf(stage);
    return s === "replied" || s === "results" ? s : null;
  }
  const status = effectiveStatus(p, d);
  if (status === "NEEDS_REVIEW") return "doctor";
  if (status !== "ELIGIBLE" || p.next === "WAIT" || p.next === "DO_NOT_CONTACT") return null;
  return "invite";
}

/** Patients-view filter group. */
export function phaseOf(p) {
  const d = store.get(p.id);
  if (taskOf(p)) return "todo";
  if (d.override === "EXCLUDED") return "done";
  const stage = stageOf(p);
  if (stage && (isFinal(stage) || stage === "result")) return "done";
  if (stage || p.next === "WAIT") return "running";
  return effectiveStatus(p, d) === "ELIGIBLE" ? "running" : "excluded";
}

/** This week's batch = invite section minus rows the practice skipped. */
export const batchOf = (patients) => patients.filter((p) => taskOf(p) === "invite" && !store.get(p.id).skipped)
  .sort((a, b) => !!store.get(b.id).draft - !!store.get(a.id).draft);

/** Index of the reached journey step (-1 = not invited yet). */
export const journeyIndex = (stage) => JOURNEY.findIndex((j) => j.stages.includes(stage));

export function addDays(date, days) {
  if (!days || !date) return null;
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const nextScreening = (result, date) => addDays(date, RESULTS[result]?.nextDays);

/** Date of the next screening LDCT after a recorded result (negative: 2 years), or null. */
export function rescreenDue(p) {
  const d = store.get(p.id);
  if (stageOf(p) !== "result") return null;
  const ev = [...(d.journey || [])].reverse().find((e) => e.stage === "result" && !e.ignored);
  return nextScreening(d.result, ev?.date);
}

/** Last recorded event with the given stage (for "when / how did they answer"). */
export const lastEvent = (p, stage) => [...(store.get(p.id).journey || [])].reverse().find((e) => !stage || e.stage === stage);

/** Channel and variant to use; an included-by-doctor patient gets the default first invite. */
export function plannedContact(p) {
  const draft = store.get(p.id).draft;
  if (stageOf(p) === "result") return { channel: draft?.channel || p.channel || "sms", variant: "RESCREEN" };
  if (draft?.channel) return { channel: draft.channel, variant: p.variant || "FIRST_INVITE" };
  if (p.channel) return { channel: p.channel, variant: p.variant || "FIRST_INVITE" };
  return { channel: p.portal ? "portal" : (p.pref === "letter" ? "letter" : "sms"), variant: "FIRST_INVITE" };
}

export const failedChannels = (p) => new Set(p.history.filter((h) => h.delivery === "failed").map((h) => h.channel));

export const practices = (patients) => [...new Set(patients.map((p) => p.gp).filter(Boolean))].sort();

export const daysBetween = (a, b) => (a && b ? Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 864e5) : 0);

/** Why this patient is getting lost, or null. plans: next automatic touch per patient (undefined = not known locally).
 *  Returns {code, days, sev: "warn" | "late"}. */
export function lostOf(p, clock, plans) {
  const d = store.get(p.id);
  const stage = stageOf(p);
  if (!stage || stage === "excluded" || stage === "result" || stage === "declined") return null;
  const journey = d.journey || [];
  const last = [...journey].reverse().find((e) => e.stage && !e.ignored);
  const since = daysBetween(last?.date, clock);
  const lastSend = [...journey].reverse().find((e) => e.stage === "sent");
  const failed = journey.some((e) => !e.stage && e.delivery === "failed" && lastSend && e.date >= lastSend.date);
  if (stage === "booked" && since >= LOST.booked) return { code: "booked", days: since, sev: since >= LOST.bookedLate ? "late" : "warn" };
  if (stage === "ldct" && since >= LOST.ldct) return { code: "ldct", days: since, sev: "warn" };
  if (stage === "nurse_call" && since >= LOST.replied) return { code: "nurse", days: since, sev: "warn" };
  if (["interested", "callback"].includes(stage) && since >= LOST.replied) return { code: "replied", days: since, sev: "warn" };
  if (stage === "sent" && failed) return { code: "failed", days: since, sev: "warn" };
  if (plans && stage === "sent" && !plans[p.id]) return { code: "exhausted", days: since, sev: "warn" };
  if (stage === "not_now" && since > LOST.pause && plans && !plans[p.id]) return { code: "pause", days: since, sev: "warn" };
  return null;
}

/** Who is responsible for the patient right now. One answer for every counter, badge, summary and filter:
 *  lost (getting lost, nurse must act) | nurse | doctor | system (the contact plan or a pause runs) | done | out (not in the programme). */
export function ownerOf(p, clock, plans) {
  const d = store.get(p.id);
  const stage = stageOf(p);
  if (lostOf(p, clock, plans)) return "lost";
  if (stage === "result") {
    if (taskOf(p) === "invite") return d.skipped ? "system" : "nurse";
    return d.result !== "negative" && !d.resultAck ? "doctor" : "done";
  }
  if (stage === "declined" || stage === "excluded") return "done";
  const task = taskOf(p);
  if (task === "doctor") return "doctor";
  if (task === "invite") return d.skipped ? "system" : "nurse";
  if (task) return "nurse";
  if (stage) return "system";
  return effectiveStatus(p, d) === "ELIGIBLE" ? "system" : "out";
}
