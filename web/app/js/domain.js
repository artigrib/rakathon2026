// Maps engine output + practice decisions to worklist buckets and journey stages. Pure functions.
import { JOURNEY, RESULTS } from "./config.js";
import { store } from "./state.js";

const effectiveStatus = (p, d) => (d.override === "ELIGIBLE" ? "ELIGIBLE" : p.status);

/** Current journey stage; a patient who replied "interested" in the source data starts at "interested". */
export function stageOf(p) {
  const d = store.get(p.id);
  if (d.stage) return d.stage;
  return effectiveStatus(p, d) === "ELIGIBLE" && p.next === "GP_REFERRAL" ? "interested" : null;
}

export function bucketOf(p) {
  const d = store.get(p.id);
  if (d.override === "EXCLUDED") return "waiting";
  const stage = stageOf(p);
  if (["booked", "ldct", "result"].includes(stage)) return "journey";
  if (["interested", "callback", "nurse_call"].includes(stage)) return "interested";
  if (stage) return "waiting"; // sent, not_now, declined
  const status = effectiveStatus(p, d);
  if (status === "NEEDS_REVIEW") return "review";
  if (status !== "ELIGIBLE") return "notEligible";
  if (p.next === "WAIT" || p.next === "DO_NOT_CONTACT") return "waiting";
  return "contact";
}

/** This week's batch = contact bucket minus rows the practice skipped. */
export const batchOf = (patients) => patients.filter((p) => bucketOf(p) === "contact" && !store.get(p.id).skipped);

/** Index of the reached journey step (-1 = not invited yet). */
export const journeyIndex = (stage) => JOURNEY.findIndex((j) => j.stages.includes(stage));

export function nextScreening(result, date) {
  const days = RESULTS[result]?.nextDays;
  if (!days || !date) return null;
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Channel and variant to use; an included-by-doctor patient gets the default first invite. */
export function plannedContact(p) {
  if (p.channel) return { channel: p.channel, variant: p.variant || "FIRST_INVITE" };
  return { channel: p.portal ? "portal" : (p.pref === "letter" ? "letter" : "sms"), variant: "FIRST_INVITE" };
}

export const failedChannels = (p) => new Set(p.history.filter((h) => h.delivery === "failed").map((h) => h.channel));

export const practices = (patients) => [...new Set(patients.map((p) => p.gp).filter(Boolean))].sort();
