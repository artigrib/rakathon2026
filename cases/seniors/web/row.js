// Row content of one senior: what is going on (describe) and what the operator or social worker can do (actions).
// The row frame, simulated answers and compose are core (core/components/row.js).
import { T } from "./i18n.js";
import { fmtDate } from "core/util.js";
import { btn, stepBtn } from "core/components/row.js";
import { allowed } from "core/fsm.js";
import { alertOf, callsOf, clock, dueToday, itemLabel, lastAnswered, latestMood, missedStreak, openNeeds, pauseOf, plannedContact, stageDate, stageOf } from "./domain.js";

const S = T.state;
const A = T.actions;
const ISO = /^\d{4}-\d{2}-\d{2}$/;
const HHMM = /^\d{1,2}:\d{2}$/;

/** "Další krok dnes 11:00: hovor asistenta" / "Další krok za 1 h: hovor asistenta" / "Další krok 21. 10. 2026 09:00: návštěva".
 *  plan = next automatic touch from /api/state (cadence.adjust adds `at`: "HH:MM", "za 1 h", "ihned"). */
export function nextStep(plan) {
  if (!plan) return "";
  const at = plan.at || "";
  const today = !clock() || plan.due <= clock(); // a due day that passed (the demo clock moves by days) is "now"
  const day = today ? (at && !HHMM.test(at) ? "" : S.today) : fmtDate(plan.due); // "za 1 h" / "ihned" say it themselves
  return S.next([day, at].filter(Boolean).join(" "), T.channel[plan.channel] || plan.channel);
}

/** A pause date or the senior's own words ("do neděle"); nothing when unknown. */
const pauseUntil = (u) => (!u ? "" : ISO.test(u) ? fmtDate(u) : String(u));
let current = null; // stage of the row being drawn: only events the state machine allows get a button
const step = (id, ev, label, kind = "", extra = "") => stepBtn(current, id, ev, label, kind, extra);
// "Vyřešeno" is the case action "resolve" (actions.js): the journey event plus closing the senior's open needs in the basket.
const resolve = (id, kind = "") => (allowed(current, "resolve") ? btn(A.resolve, `data-action="resolve" data-id="${id}"`, kind) : "");

export const rowClass = (p, d) => (d.skipped && dueToday(p) ? " row--skipped" : "");

const quote = (c) => (c?.text ? `„${c.text}“` : "");
const when = (c) => (c ? S.answered(fmtDate(c.date), c.time, S.via[c.via]) : "");

/** One sentence about the senior's state (also used by the tiles and the card). */
export function stateLine(p, d, plan) {
  const stage = stageOf(p);
  const last = lastAnswered(p);
  switch (stage) {
    case "no_answer": {
      const calls = callsOf(p);
      const day = calls[0]?.date;
      const heard = calls.findIndex((c) => c.answered);
      const streak = heard < 0 ? calls : calls.slice(0, heard); // calls since the last answer
      const n = streak.filter((c) => !c.relative).length || p.missed || 1;
      const relative = streak.some((c) => c.relative) || p.calls?.at(-1)?.relative;
      const next = plan ? nextStep(plan) : relative ? S.relativeSent : "";
      return { title: S.noAnswer(n, fmtDate(day)), sub: next };
    }
    case "escalated": {
      const why = alertOf(p);
      const title = why === "crisis" ? S.crisis : why === "emergency" ? S.emergency : why === "health" ? S.health : why === "visit" ? S.visit(p, missedStreak(p)) : S.escalated;
      return { title, sub: why === "visit" || why === "escalate" ? fmtDate(stageDate(p)) : [quote(last), when(last)].filter(Boolean).join(" ") };
    }
    case "low_mood": return { title: S.lowMood(last?.mood), sub: [quote(last), when(last)].filter(Boolean).join(" ") };
    case "needs_help": {
      const items = [...new Set(openNeeds(p).map((n) => itemLabel(n.item)))];
      return { title: items.length ? S.needs(items.join(", ")) : S.needsAny, sub: [quote(last), when(last)].filter(Boolean).join(" ") };
    }
    case "callback": return { title: last?.intent === "question" || last?.intent === "unclear" ? S.question : S.callback, sub: [quote(last), when(last)].filter(Boolean).join(" ") };
    case "ok": return { title: S.ok(last?.mood || latestMood(p)), sub: when(last) };
    case "resolved": return { title: S.resolved(fmtDate(stageDate(p))), sub: last ? `${T.intent[last.intent] || ""}, ${when(last)}` : "" };
    case "paused": {
      const pause = pauseOf(p);
      const reason = (pause?.reason || "").replace(/[.!\s]+$/, "");
      const until = pauseUntil(pause?.until).replace(/^do\s+/i, ""); // the senior's words "do neděle" already say "do"
      return { title: S.paused(reason, until && !reason.toLowerCase().includes(until.toLowerCase()) ? until : "") };
    }
    case "declined": return { title: S.declined, sub: last?.intent === "opt_out" ? quote(last) : "" };
    default: return { title: S.enrolled(p, p.schedule ? `${T.schedule[p.schedule.kind]} ${T.schedule.window(p.schedule)}` : "") };
  }
}

/** {title, sub}: today's call first (when it is due and nothing more urgent is going on), else the state. */
export function describe(p, d, plan) {
  const st = stateLine(p, d, plan);
  const stage = stageOf(p);
  if (dueToday(p) && ["ok", "resolved", "enrolled", "new", null].includes(stage)) {
    if (d.skipped) return { title: S.dueSkipped, sub: st.title };
    return { title: S.due(p.schedule, T.channel[plannedContact(p).channel]), sub: d.draft ? S.edited : st.title };
  }
  return st;
}

export function actions(p, d) {
  const id = p.id;
  const stage = stageOf(p);
  current = stage || "new";
  const today = dueToday(p) ? (d.skipped ? btn(A.unskip, `data-action="unskip" data-id="${id}"`, "link")
    : btn(A.call, `data-action="open-compose" data-id="${id}"`) + btn(A.skip, `data-action="skip" data-id="${id}"`, "link")) : "";
  switch (stage) {
    case "escalated": return resolve(id, "primary");
    case "low_mood": return step(id, "escalate", A.escalate, "primary") + resolve(id, "link");
    // today's call of these goes out with the batch; the row keeps only the one decision that is specific to it
    case "needs_help": return btn(A.basket, `data-action="pick-view" data-view="basket"`) + resolve(id, "link");
    case "callback": return btn(A.call, `data-action="open-compose" data-id="${id}"`, "primary") + resolve(id, "link");
    case "no_answer": return step(id, "visit", A.visit) + step(id, "ok", A.reached, "link");
    case "paused": return step(id, "resume", A.resume, "link");
    case "declined": return step(id, "enroll", A.enroll, "link");
  }
  return today || step(id, "pause", A.pause, "link");
}
