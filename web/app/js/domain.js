// What the practice has to do about each patient. Pure functions over engine output + recorded decisions.
import { JOURNEY, RESULTS } from "./config.js";
import { store } from "./state.js";

const effectiveStatus = (p, d) => (d.override === "ELIGIBLE" ? "ELIGIBLE" : p.status);

/** Current journey stage; a patient who replied "interested" in the source data starts at "interested". */
export function stageOf(p) {
  const d = store.get(p.id);
  if (d.stage) return d.stage;
  return effectiveStatus(p, d) === "ELIGIBLE" && p.next === "GP_REFERRAL" ? "interested" : null;
}

/** Work-queue section for the patient, or null when nothing needs doing right now. */
export function taskOf(p) {
  const d = store.get(p.id);
  if (d.override === "EXCLUDED") return null;
  const stage = stageOf(p);
  if (["interested", "callback", "nurse_call"].includes(stage)) return "replied";
  if (["booked", "ldct"].includes(stage)) return "results";
  if (stage) return null; // sent, not_now, declined, result: the system or the patient is on the move
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
  if (["result", "declined"].includes(stage)) return "done";
  if (stage || p.next === "WAIT") return "running";
  return effectiveStatus(p, d) === "ELIGIBLE" ? "running" : "excluded";
}

/** This week's batch = invite section minus rows the practice skipped. */
export const batchOf = (patients) => patients.filter((p) => taskOf(p) === "invite" && !store.get(p.id).skipped);

/** Index of the reached journey step (-1 = not invited yet). */
export const journeyIndex = (stage) => JOURNEY.findIndex((j) => j.stages.includes(stage));

export function addDays(date, days) {
  if (!days || !date) return null;
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const nextScreening = (result, date) => addDays(date, RESULTS[result]?.nextDays);

/** Last recorded event with the given stage (for "when / how did they answer"). */
export const lastEvent = (p, stage) => [...(store.get(p.id).journey || [])].reverse().find((e) => !stage || e.stage === stage);

/** Channel and variant to use; an included-by-doctor patient gets the default first invite. */
export function plannedContact(p) {
  const draft = store.get(p.id).draft;
  if (draft?.channel) return { channel: draft.channel, variant: p.variant || "FIRST_INVITE" };
  if (p.channel) return { channel: p.channel, variant: p.variant || "FIRST_INVITE" };
  return { channel: p.portal ? "portal" : (p.pref === "letter" ? "letter" : "sms"), variant: "FIRST_INVITE" };
}

export const failedChannels = (p) => new Set(p.history.filter((h) => h.delivery === "failed").map((h) => h.channel));

export const practices = (patients) => [...new Set(patients.map((p) => p.gp).filter(Boolean))].sort();
