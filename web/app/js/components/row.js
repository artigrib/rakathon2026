// One record = one row: who · what is going on (one sentence) · what to do (one main action).
// What the sentence and the buttons are is the case's business (web/row.js: describe, actions).
import { CASE, T, cfg, dom, rows } from "../case.js";
import { esc } from "../util.js";
import { store } from "../state.js";
import { allowed } from "../fsm.js";
import { compose } from "./compose.js";

/** A button; attrs are raw attributes (data-action="…" data-id="…"). kind: primary | link | "". */
export const btn = (label, attrs, kind = "") => `<button type="button" class="btn${kind ? ` btn--${kind}` : ""}" ${attrs}>${esc(label)}</button>`;

/** Button for a journey event, only when the state machine allows it in `state` (click → action "step"). */
export const stepBtn = (state, id, ev, label, kind = "", extra = "") =>
  allowed(state, ev) ? btn(label, `data-action="step" data-stage="${ev}" data-id="${id}" ${extra}`, kind) : "";

function demoReplies(p, link) {
  return `<div class="replies"><span>${T.demo.replyLabel}</span>${cfg.REPLIES.map((r) =>
    `<button type="button" data-action="reply" data-reply="${r}" data-id="${p.id}">${T.demo.reply[r]}</button>`).join("")}${
    link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${T.demo.openLink}</a>` : ""}</div>`;
}

export function row(p, { composing, chosenChannel, plan, link, demo, open, outbox, lost }) {
  const d = store.get(p.id);
  const { title, sub } = rows.describe(p, d, plan);
  const why = lost ? T.lost[lost.code](lost.days, p) : "";
  // simulated replies while we wait for one; a case may keep them out of the rows (case.json "row_demo": false → its card shows them)
  const showDemo = demo && CASE.row_demo !== false && dom.stageOf(p) === CASE.sent_stage;
  return `<article class="row${rows.rowClass ? rows.rowClass(p, d) : ""}" id="pt-${p.id}">
    <div class="row__main">
      <button type="button" class="who" data-action="open-card" data-id="${p.id}" aria-haspopup="dialog" title="${T.actions.open}">${esc(T.who(p))}</button>
      <div class="what">${why ? `<em class="lostwhy">${esc(why)}</em>` : ""}<b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}${showDemo ? demoReplies(p, link) : ""}</div>
      <div class="actions">${rows.actions(p, d)}</div>
    </div>
    ${composing && !open ? compose(p, chosenChannel) : ""}
  </article>`;
}
