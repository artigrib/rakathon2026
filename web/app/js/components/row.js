// One patient = one row: who · what is going on (one sentence) · what to do (one main action).
import { REPLIES } from "../config.js";
import { T } from "../i18n/cs.js";
import { cap, esc, fmtDate } from "../util.js";
import { addDays, lastEvent, nextScreening, plannedContact, stageOf, taskOf } from "../domain.js";
import { store } from "../state.js";
import { allowed } from "../fsm.js";
import { compose } from "./compose.js";
import { detail } from "./detail.js";

const S = T.state;
const A = T.actions;
const btn = (label, attrs, kind = "") => `<button type="button" class="btn${kind ? ` btn--${kind}` : ""}" ${attrs}>${esc(label)}</button>`;
let current = null; // stage of the row being drawn: only events the state machine allows get a button
const step = (id, ev, label, kind = "", extra = "") =>
  allowed(current, ev) ? btn(label, `data-action="step" data-stage="${ev}" data-id="${id}" ${extra}`, kind) : "";

/** {title, sub}: what is going on with the patient, in plain words. */
function describe(p, d, plan) {
  if (stageOf(p) === "excluded") return { title: S.excluded(p) };
  const stage = stageOf(p);
  const ev = lastEvent(p, stage);
  const answered = ev?.date ? S.replied(fmtDate(ev.date), S.via[ev.via]) : "";
  switch (stage) {
    case "sent": {
      const del = [...(d.journey || [])].reverse().find((e) => e.delivery)?.delivery;
      const next = plan ? S.sentNext(fmtDate(plan.due), T.channel[plan.channel]) : S.sentWait;
      return { title: S.sent(fmtDate(d.sent.date), T.channel[d.sent.channel]) + (del ? `, ${T.detail.delivery[del] || del}` : ""), sub: next };
    }
    case "interested":
    case "callback":
      return { title: S[stage] + (ev?.when ? `, ${ev.when}` : ""), sub: answered };
    case "nurse_call": return { title: S.nurse_call(p) };
    case "not_now": {
      const again = fmtDate(addDays(ev?.date, 90));
      const unreachable = ev?.via === "ui" && ev?.event === "not_now" && !ev?.text;
      const title = ev?.event === "no_show" ? S.noShow(p, again) : ev?.intent === "declined" ? S.softDeclined(p, again)
        : unreachable ? S.unreachable(p, again) : S.not_now(again);
      return { title, sub: answered };
    }
    case "declined": return { title: S.declined(p), sub: answered };
    case "booked": { // the nurse referred (01196) or the patient booked by themselves (reply)
      const self = ev?.text || (ev?.via && ev.via !== "ui");
      return { title: self ? S.selfBooked(p) : S.booked(p), sub: S.bookedNext };
    }
    case "ldct": return { title: S.ldct };
    case "result": return { title: S.result[d.result](fmtDate(nextScreening(d.result, ev?.date))), sub: d.resultAck ? S.resultAck : "" };
  }
  const task = taskOf(p);
  if (task === "invite") return d.skipped ? { title: S.skipped }
    : { title: cap(S.invite(T.channel[plannedContact(p).channel])), sub: d.draft ? S.edited : "" };
  if (task === "doctor") return { title: p.reasons.find((r) => !r.startsWith("Věk")) || T.status.NEEDS_REVIEW };
  if (p.status === "ELIGIBLE") return { title: p.why || T.status.ELIGIBLE };
  return { title: T.status[p.status] };
}

function actions(p, d) {
  const id = p.id;
  const stage = stageOf(p);
  if (stage === "excluded") return btn(A.include, `data-action="include" data-id="${id}"`, "link");
  current = stage;
  switch (stage) {
    case "interested":
      return step(id, "booked", A.booked, "primary") + step(id, "declined", A.declined) + step(id, "not_now", A.unreachable, "link");
    case "sent":
    case "not_now": // waiting: the patient may call the practice, or the nurse wants to try again now
      return step(id, "interested", A.interested, "link") + btn(A.again, `data-action="open-compose" data-id="${id}"`, "link");
    case "declined":
      return step(id, "interested", A.changedMind, "link");
    case "result":
      return d.result !== "negative" && !d.resultAck ? btn(A.ack, `data-action="ack" data-id="${id}"`) : "";
    case "callback":
    case "nurse_call":
      return step(id, "interested", A.interested, "primary") + step(id, "declined", A.declined) + step(id, "not_now", A.unreachable, "link");
    case "booked":
      return step(id, "ldct", A.ldct, "primary") + step(id, "no_show", A.noShow, "link");
    case "ldct":
      return Object.entries(A.result).map(([k, label]) => step(id, "result", label, "", `data-result="${k}"`)).join("");
  }
  if (stage) return "";
  switch (taskOf(p)) {
    case "invite":
      return d.skipped ? btn(A.unskip, `data-action="unskip" data-id="${id}"`, "link")
        : btn(A.edit, `data-action="open-compose" data-id="${id}"`) + btn(A.skip, `data-action="skip" data-id="${id}"`, "link");
    case "doctor":
      return btn(A.include, `data-action="include" data-id="${id}"`) + btn(A.exclude, `data-action="exclude" data-id="${id}"`);
  }
  return p.status !== "ELIGIBLE" ? btn(A.exception, `data-action="include" data-exception="1" data-id="${id}"`, "link") : "";
}

function demoReplies(p, link) {
  return `<div class="replies"><span>${T.demo.replyLabel}</span>${REPLIES.map((r) =>
    `<button type="button" data-action="reply" data-reply="${r}" data-id="${p.id}">${T.demo.reply[r]}</button>`).join("")}${
    link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${T.demo.openLink}</a>` : ""}</div>`;
}

export function row(p, { composing, chosenChannel, plan, link, demo, open, outbox, lost }) {
  const d = store.get(p.id);
  const { title, sub } = describe(p, d, plan);
  const why = lost ? T.lost[lost.code](lost.days, p) : "";
  const showDemo = demo && stageOf(p) === "sent";
  return `<article class="row${d.skipped && taskOf(p) === "invite" ? " row--skipped" : ""}" id="pt-${p.id}">
    <div class="row__main">
      <button type="button" class="who" data-action="toggle-detail" data-id="${p.id}" aria-expanded="${!!open}" title="${A.open}">${esc(T.who(p))}</button>
      <div class="what">${why ? `<em class="lostwhy">${esc(why)}</em>` : ""}<b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}${showDemo ? demoReplies(p, link) : ""}</div>
      <div class="actions">${actions(p, d)}</div>
    </div>
    ${composing ? compose(p, chosenChannel) : ""}
    ${open ? detail(p, d, { plan, outbox }) : ""}
  </article>`;
}
