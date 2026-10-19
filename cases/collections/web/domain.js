// Who is on turn for each debtor and what the system does next. Pure functions over the record (segment and strategy
// come precomputed from ../strategy.py via build.py) and the recorded decisions (journey, promises, plan …).
import { AUTOMATED, CONTACT_HOURS, EASTER, FIXED_HOLIDAYS, LOST_DAYS, OFFER_DAYS, PLAN_MIN_INSTALMENT, PLAN_MONTHS, PORTFOLIOS,
  REFI_RATE, REFI_TERMS, WEEKLY_CAP } from "./config.js";
import { CASE } from "core/case.js";
import { store } from "core/state.js";

let CLOCK = null;
export const setClock = (c) => { CLOCK = c; };
export const clock = () => CLOCK;

const HUMAN_STAGES = ["human_handoff", "wrong_contact", "refi_accepted"];
const DONE = ["paid", "do_not_contact", "closed"];
const SYSTEM = ["contacted", "broken_promise", "promise_to_pay", "plan_offered", "plan_active", "refi_offered"];

/** Current stage; null = new (not contacted yet). */
export function stageOf(p) {
  return store.get(p.id).stage || null;
}

/** Effective segment / strategy: a dispute or hardship recorded in the journey overrides the stored rule result. */
export function segmentOf(p) {
  const s = stageOf(p);
  if (s === "dispute") return "dispute";
  if (s === "hardship_review") return "vulnerable";
  return p.segment;
}
export const strategyOf = (p) => ({ dispute: "human", vulnerable: "human" }[segmentOf(p)] || p.strategy);
export const automated = (p) => AUTOMATED.includes(strategyOf(p));

// ---------- money ----------
export const payments = (d) => d.payments || [];
export const paidTotal = (d) => payments(d).reduce((a, x) => a + (+x.amount || 0), 0);
export const remaining = (p, d = store.get(p.id)) => (d.stage === "paid" ? 0 : Math.max(0, (p.outstanding || 0) - paidTotal(d)));
/** Recovered in the demo: payments, or the whole outstanding amount when an operator marked it paid. */
export const recovered = (p, d = store.get(p.id)) => (d.stage === "paid" ? Math.max(p.outstanding || 0, paidTotal(d)) : paidTotal(d));

export function planOptions(amount) {
  return PLAN_MONTHS.map((n) => ({ n, monthly: Math.ceil(amount / n) })).filter((o) => o.n <= 3 || o.monthly >= PLAN_MIN_INSTALMENT);
}
const annuity = (pr, m) => { const q = REFI_RATE / 12; return Math.ceil((pr * q) / (1 - (1 + q) ** -m)); };
/** Same as strategy.refi_example (illustrative, not an offer). */
export function refiExample(amount) {
  const months = REFI_TERMS.find((t) => annuity(amount, t) <= Math.max(1500, amount / 30)) || REFI_TERMS.at(-1);
  const monthly = annuity(amount, months);
  return { principal: amount, months, monthly, total: monthly * months, rate: Math.round(REFI_RATE * 1000) / 10,
    rpsn: Math.round(((1 + REFI_RATE / 12) ** 12 - 1) * 1000) / 10 };
}

// ---------- dates and the contact window (same rules as cadence.py) ----------
export const addDays = (iso, n) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
export const daysBetween = (a, b) => (a && b ? Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 864e5) : 0);
export function isHoliday(iso) {
  const md = iso.slice(5);
  if (FIXED_HOLIDAYS.includes(md)) return true;
  const e = EASTER[iso.slice(0, 4)];
  if (!e) return false;
  const easter = `${iso.slice(0, 4)}-${e}`;
  return iso === addDays(easter, -2) || iso === addDays(easter, 1);
}
export const isContactDay = (iso) => !!iso && new Date(`${iso}T00:00:00Z`).getUTCDay() % 6 !== 0 && !isHoliday(iso);
export const contactHours = CONTACT_HOURS;
export const sends = (d) => (d.journey || []).filter((e) => e.stage === CASE.sent_stage && (!e.event || e.event === "send"));
export const contactsInWeek = (d, day) => sends(d).filter((e) => daysBetween(e.date, day) >= 0 && daysBetween(e.date, day) <= 6).length;
export const weeklyCap = WEEKLY_CAP;
/** Channels the client refused: "all" (STOP) or a list. */
export function blockedChannels(d) {
  if (d.optout === "all" || d.stage === "do_not_contact") return "all";
  return Array.isArray(d.optout) ? d.optout : [];
}
/** May the operator send this client a message today (demo clock)? */
export function canContact(p, day = CLOCK) {
  const d = store.get(p.id);
  return isContactDay(day) && contactsInWeek(d, day) < WEEKLY_CAP && blockedChannels(d) !== "all" && !d.contactInvalid;
}

// ---------- promises and plans ----------
export const promisesOf = (d) => d.promises || [];
export const openPromise = (d) => [...promisesOf(d)].reverse().find((x) => x.status === "open") || null;
export const lastEvent = (p, stage) => [...(store.get(p.id).journey || [])].reverse().find((e) => !e.ignored && (!stage || e.stage === stage));

// ---------- the contract of cases/README.md ----------
/** Who is on turn: operator | supervisor | system | done | lost. */
export function ownerOf(p, clk, plans) {
  const s = stageOf(p);
  if (DONE.includes(s)) return "done";
  if (lostOf(p, clk, plans)) return "lost";
  if (s === "dispute" || s === "hardship_review") return "supervisor";
  if (HUMAN_STAGES.includes(s)) return "operator";
  if (SYSTEM.includes(s)) return "system";
  // new: automated strategies wait for the operator's approval of the first message, others go to a person
  if (strategyOf(p) === "supervisor" || strategyOf(p) === "human") return "supervisor";
  return store.get(p.id).skipped ? "system" : "operator";
}

/** Why a client is getting lost, or null: {code, days, sev}. */
export function lostOf(p, clk, plans) {
  const d = store.get(p.id);
  const s = stageOf(p);
  const last = lastEvent(p);
  const since = daysBetween(last?.date, clk);
  if (HUMAN_STAGES.includes(s) && since >= LOST_DAYS) return { code: "waiting", days: since, sev: since >= 2 * LOST_DAYS ? "late" : "warn" };
  if (s === "contacted") {
    const lastSend = sends(d).at(-1);
    const failed = (d.journey || []).some((e) => !e.stage && e.delivery === "failed" && lastSend && e.date >= lastSend.date);
    if (failed) return { code: "failed", days: since, sev: "warn" };
    if (plans && !plans[p.id]) return { code: "exhausted", days: since, sev: "warn" };
  }
  return null;
}

/** Channel and text variant of the next manual / batch message. */
export function plannedContact(p) {
  const d = store.get(p.id);
  const blocked = blockedChannels(d);
  const okCh = (c) => blocked !== "all" && !blocked.includes(c);
  const pref = d.draft?.channel || p.pref || "sms";
  const channel = okCh(pref) ? pref : ["sms", "email", "whatsapp", "voice"].find(okCh) || "sms";
  return { channel, variant: stageOf(p) === "broken_promise" ? "BROKEN_PROMISE" : "FIRST_INVITE" };
}

/** What "approve-batch" sends: new clients of automated strategies, not skipped, contact allowed today. */
export const batchOf = (records) => records.filter((p) => !stageOf(p) && automated(p) && !store.get(p.id).skipped && canContact(p))
  .sort((a, b) => !!store.get(b.id).draft - !!store.get(a.id).draft);

export const failedChannels = (p) => new Set((p.history || []).filter((h) => h.delivery === "failed").map((h) => h.channel));

export const groups = (records) => PORTFOLIOS.filter((g) => records.some((p) => p.portfolio === g));

/** Same as hooks.extra_placeholders: never an amount or any detail of the debt. */
export function placeholders(p, M) {
  const s = p.strategy || "reminder";
  const P = M.parts;
  return { creditor: P.creditor, offer_sms: P.offer_sms[s] ?? P.offer_sms.reminder,
    offer_email: P.offer_email[s] ?? P.offer_email.reminder, offer_voice: P.offer_voice[s] ?? P.offer_voice.reminder };
}

/** Queue section (Fronta) of a client, or null when nothing needs a person now. */
export function queueOf(p) {
  const s = stageOf(p);
  if (s === "dispute" || s === "hardship_review") return "human";
  if (HUMAN_STAGES.includes(s)) return "operator";
  if (s) return null;
  return strategyOf(p);
}
