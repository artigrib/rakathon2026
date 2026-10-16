// One patient = one row: who · what is going on (one sentence) · what to do (one main action).
import { REPLIES } from "../config.js";
import { T } from "../i18n/cs.js";
import { cap, esc, fmtDate } from "../util.js";
import { addDays, lastEvent, nextScreening, plannedContact, stageOf, taskOf } from "../domain.js";
import { store } from "../state.js";
import { compose } from "./compose.js";
import { detail } from "./detail.js";

const S = T.state;
const A = T.actions;
const btn = (label, attrs, kind = "") => `<button type="button" class="btn${kind ? ` btn--${kind}` : ""}" ${attrs}>${esc(label)}</button>`;
const step = (id, stage, label, kind = "", extra = "") => btn(label, `data-action="step" data-stage="${stage}" data-id="${id}" ${extra}`, kind);

/** {title, sub}: what is going on with the patient, in plain words. */
function describe(p, d, plan) {
  if (d.override === "EXCLUDED") return { title: S.excluded };
  const stage = stageOf(p);
  const ev = lastEvent(p, stage);
  const answered = ev?.date ? S.replied(fmtDate(ev.date), S.via[ev.via]) : "";
  switch (stage) {
    case "sent":
      return { title: S.sent(fmtDate(d.sent.date), T.channel[d.sent.channel]),
               sub: plan ? S.sentNext(fmtDate(plan.due), T.channel[plan.channel]) : S.sentWait };
    case "interested":
    case "callback":
      return { title: S[stage] + (ev?.when ? `, ${ev.when}` : ""), sub: answered };
    case "nurse_call": return { title: S.nurse_call };
    case "not_now": return { title: S.not_now(fmtDate(addDays(ev?.date, 90))), sub: answered };
    case "declined": return { title: S.declined, sub: answered };
    case "booked": return { title: S.booked, sub: S.bookedNext };
    case "ldct": return { title: S.ldct };
    case "result": return { title: S.result[d.result](fmtDate(nextScreening(d.result, ev?.date))) };
  }
  const task = taskOf(p);
  if (task === "invite") return d.skipped ? { title: S.skipped } : { title: cap(S.invite(T.channel[plannedContact(p).channel])) };
  if (task === "doctor") return { title: p.reasons.find((r) => !r.startsWith("Věk")) || T.status.NEEDS_REVIEW };
  if (p.status === "ELIGIBLE") return { title: p.why || T.status.ELIGIBLE };
  return { title: T.status[p.status] };
}

function actions(p, d) {
  const id = p.id;
  if (d.override === "EXCLUDED") return "";
  const stage = stageOf(p);
  switch (stage) {
    case "interested":
      return step(id, "booked", A.booked, "primary") + step(id, "declined", A.declined);
    case "callback":
    case "nurse_call":
      return step(id, "interested", A.interested, "primary") + step(id, "declined", A.declined) + step(id, "not_now", A.unreachable, "link");
    case "booked":
      return step(id, "ldct", A.ldct, "primary");
    case "ldct":
      return Object.entries(A.result).map(([k, label]) => step(id, "result", label, "", `data-result="${k}"`)).join("");
  }
  if (stage) return "";
  switch (taskOf(p)) {
    case "invite":
      return d.skipped ? btn(A.unskip, `data-action="unskip" data-id="${id}"`, "link")
        : btn(A.edit, `data-action="open-compose" data-id="${id}"`, "link") + btn(A.skip, `data-action="skip" data-id="${id}"`, "link");
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

export function row(p, { composing, chosenChannel, plan, link, demo, open }) {
  const d = store.get(p.id);
  const { title, sub } = describe(p, d, plan);
  const showDemo = demo && stageOf(p) === "sent";
  return `<article class="row${d.skipped && taskOf(p) === "invite" ? " row--skipped" : ""}" id="pt-${p.id}">
    <div class="row__main">
      <button type="button" class="who" data-action="toggle-detail" data-id="${p.id}" aria-expanded="${!!open}" title="${A.open}">${esc(T.who(p))}</button>
      <div class="what"><b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}${showDemo ? demoReplies(p, link) : ""}</div>
      <div class="actions">${actions(p, d)}</div>
    </div>
    ${composing ? compose(p, chosenChannel) : ""}
    ${open ? detail(p, d) : ""}
  </article>`;
}
