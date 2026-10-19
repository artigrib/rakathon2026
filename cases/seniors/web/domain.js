// Who has to do what about each senior. Pure functions over the registry record (calls of the last 30 days) and the
// recorded journey (calls of this demo, answers, decisions of the operator and the social worker).
import { BASKET, LOST, NO_CALL } from "./config.js";
import { CASE, contentUrl } from "core/case.js";
import { store } from "core/state.js";

// Needs and mood vocabulary, shared with dialog.py (../items.json, served as content/items.json).
const VOCAB = await (await fetch(contentUrl("items.json"))).json();
export const ITEMS = VOCAB.items;
export const itemLabel = (k) => ITEMS[k]?.label || k;

let CLOCK = null;
export const setClock = (c) => { CLOCK = c; };
export const clock = () => CLOCK;

const SENT = CASE.sent_stage;

export function addDays(date, days) {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
export const daysBetween = (a, b) => (a && b ? Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 864e5) : 0);
/** 0 = Monday … 6 = Sunday. */
export const weekday = (iso) => (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;

// ---------- reading answers (static mode has no backend: the same vocabulary as dialog.extract) ----------
const norm = (t) => (t || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
const RE = Object.fromEntries(Object.entries(ITEMS).map(([k, v]) => [k, v.patterns.map((p) => new RegExp(p))]));
const MOOD = Object.entries(VOCAB.mood).map(([m, ps]) => [+m, ps.map((p) => new RegExp(p))]);
const HEALTH = VOCAB.health.map((p) => new RegExp(p));

export function extract(text) {
  const t = norm(text);
  if (!t) return {};
  const out = {};
  const moods = MOOD.filter(([, ps]) => ps.some((r) => r.test(t))).map(([m]) => m);
  if (moods.length) out.mood = Math.min(...moods);
  const items = Object.keys(RE).filter((k) => RE[k].some((r) => r.test(t)));
  if (items.length) out.items = items;
  if (HEALTH.some((r) => r.test(t))) out.health_flag = true;
  return out;
}
const MOOD_OF_INTENT = { ok: 4, low_mood: 2 };

// ---------- stage ----------
/** Current stage: the recorded journey, else the stage from the registry (last call before the demo). */
export function stageOf(p) {
  return store.get(p.id).stage || p.stage || null;
}

/** Every call of a senior, newest first: the registry's 30 days + the calls and answers recorded in this demo.
 *  {date, time?, answered, intent?, text?, mood?, items?, health?, relative?, channel?, live?, via?, note?} */
export function callsOf(p) {
  const live = [];
  for (const e of store.get(p.id).journey || []) {
    if (e.event === "send" && e.stage === SENT) {
      live.push({ date: e.date, answered: false, channel: e.channel, relative: e.variant === "RELATIVE", auto: !!e.auto, live: true });
      continue;
    }
    if (!e.intent || (!e.text && e.via === "ui")) continue; // an operator's decision, not an answer
    const x = e.extra || extract(e.text);
    const answer = {
      answered: true, intent: e.intent, text: e.text || "", via: e.via, live: true, transcript: e.transcript || null,
      mood: x.mood ? +x.mood || null : MOOD_OF_INTENT[e.intent] || null,
      items: Array.isArray(x.items) ? x.items : typeof x.items === "string" ? x.items.split(/[,;]\s*/).filter(Boolean) : [],
      health: !!x.health_flag || ["health_problem", "emergency"].includes(e.intent),
    };
    if (e.intent === "need_items" && !answer.items.length) answer.items = ["jine"];
    const pending = [...live].reverse().find((c) => !c.answered && !c.relative && c.date === e.date);
    if (pending) Object.assign(pending, answer); else live.push({ date: e.date, ...answer });
  }
  return [...live.reverse(), ...[...(p.calls || [])].reverse()];
}

export const lastAnswered = (p) => callsOf(p).find((c) => c.answered);

/** Mood points [{date, mood}] of the last `days` days, oldest first. */
export function moodSeries(p, days = 30) {
  const from = addDays(CLOCK, -days);
  return callsOf(p).filter((c) => c.answered && c.mood && c.date >= from).map((c) => ({ date: c.date, mood: c.mood })).reverse();
}
export const latestMood = (p) => store.get(p.id).mood || callsOf(p).find((c) => c.answered && c.mood)?.mood || null;

// ---------- the needs basket ----------
/** Basket entries {id, item, date, status, live?}: from the registry and from answers in this demo (backend: hooks.on_reply
 *  keeps them in decisions[id].needs; static: read from the journey). Status changes are the mark "basket". */
export function needsOf(p) {
  const d = store.get(p.id);
  const live = d.needs || callsOf(p).filter((c) => c.live && c.answered && c.items?.length)
    .flatMap((c) => c.items.filter((it) => it !== "navsteva").map((it) => ({ id: `${p.id}-${c.date}-${it}`, item: it, date: c.date, status: "new" })));
  const seen = new Set();
  return [...(p.needs || []), ...live].filter((n) => !seen.has(n.id) && seen.add(n.id))
    .map((n) => ({ ...n, status: d.basket?.[n.id] || n.status }));
}
export const openNeeds = (p) => needsOf(p).filter((n) => n.status !== "done");
export const nextStatus = (s) => BASKET[Math.min(BASKET.indexOf(s) + 1, BASKET.length - 1)];

// ---------- today ----------
export const scheduledOn = (p, day) => !!p.schedule?.days?.includes(weekday(day));
const touchedOn = (p, day) => (store.get(p.id).journey || []).some((e) => e.date === day && !e.ignored && (e.event === "send" || e.intent));
/** Has a check-in call today and has not been called yet. */
export const dueToday = (p) => !!CLOCK && scheduledOn(p, CLOCK) && !NO_CALL.includes(stageOf(p)) && !touchedOn(p, CLOCK);

/** What "approve-batch" sends: today's calls minus those the operator left out. */
export const batchOf = (records) => records.filter((p) => dueToday(p) && !store.get(p.id).skipped);

export function plannedContact(p) {
  const draft = store.get(p.id).draft;
  return { channel: draft?.channel || p.channel || "voice", variant: "CHECKIN" };
}

/** Why the senior is escalated: emergency | health | visit | lowMood | escalate. */
export function alertOf(p) {
  const stage = stageOf(p);
  if (stage === "low_mood") return "lowMood";
  if (stage !== "escalated") return null;
  const e = [...(store.get(p.id).journey || [])].reverse().find((x) => x.stage === "escalated" && !x.ignored);
  if (e) return e.event === "emergency" ? "emergency" : e.event === "health_problem" ? "health" : e.event === "visit" ? "visit" : "escalate";
  const last = lastAnswered(p);
  return last?.intent === "emergency" ? "emergency" : "health";
}

/** Date of the event that set the current stage (journey or the registry's last call). */
export function stageDate(p) {
  const e = [...(store.get(p.id).journey || [])].reverse().find((x) => x.stage && !x.ignored);
  return e?.date || p.calls?.at(-1)?.date || p.since;
}

// ---------- owner ----------
/** Getting lost: {code, days, sev} or null. plans: next automatic touch per senior (undefined = not known locally). */
export function lostOf(p, clk, plans) {
  const stage = stageOf(p);
  if (!stage || ["paused", "declined", "enrolled", "new"].includes(stage)) return null;
  const since = daysBetween(stageDate(p), clk);
  if (stage === "escalated" && since >= LOST.escalated) return { code: "escalated", days: since, sev: "late" };
  const heard = lastAnswered(p);
  const silent = heard ? daysBetween(heard.date, clk) : 0;
  if (stage === SENT && (store.get(p.id).journey || []).length && plans && !plans[p.id]) return { code: "noAnswer", days: silent, sev: "warn" };
  // scheduled call days that passed without hearing the senior (a Tue/Thu senior is not lost over the weekend)
  let missed = 0;
  for (let d = heard ? addDays(heard.date, 1) : clk; heard && d < clk; d = addDays(d, 1)) missed += scheduledOn(p, d) ? 1 : 0;
  if (stage !== "escalated" && missed >= LOST.silent) return { code: "silent", days: silent, sev: "warn" };
  return null;
}

/** Who acts now: lost | social (escalated, low mood, open needs) | operator (call back, today's call, no answer and
 *  no automatic step) | system (the plan runs or all is well) | paused | done (opted out). */
export function ownerOf(p, clk, plans) {
  const stage = stageOf(p);
  if (stage === "declined") return "done";
  if (stage === "paused") return "paused";
  if (lostOf(p, clk, plans)) return "lost";
  if (stage === "escalated" || stage === "low_mood") return "social";
  if (stage === "needs_help") return openNeeds(p).length ? "social" : "system";
  if (stage === "callback") return "operator";
  if (stage === SENT) return plans?.[p.id] ? "system" : "operator";
  if (dueToday(p) && !store.get(p.id).skipped) return "operator";
  return "system";
}

/** Districts for the header selector (case.json group.field = "district"). */
export const groups = (records) => [...new Set(records.map((p) => p.district).filter(Boolean))].sort((a, b) => a.localeCompare(b, "cs"));

/** Message placeholders (same as ../hooks.py extra_placeholders). */
export const placeholders = (p) => ({ name: p.vocative ? `, ${p.vocative}` : "", senior: p.title || "Váš blízký", worker: p.worker || "" });
