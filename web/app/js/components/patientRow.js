import { BUCKETS, NO_RESPONSE_DAYS, REPLIES } from "../config.js";
import { T } from "../i18n/cs.js";
import { esc, fmtDate, html } from "../util.js";
import { bucketOf, nextScreening, plannedContact, stageOf } from "../domain.js";
import { store } from "../state.js";
import { shape } from "./shape.js";
import { compose } from "./compose.js";
import { detail } from "./detail.js";
import { journey } from "./journey.js";

const shapeOf = Object.fromEntries(BUCKETS.map((b) => [b.key, b.shape]));
const J = T.journey;
const btn = (label, attrs, cls = "btn") => `<button type="button" class="${cls}" ${attrs}>${label}</button>`;
const hint = (text) => `<span class="pt__why">${esc(text)}</span>`;
const badge = (text, kind) => `<span class="badge badge--${kind}">${esc(text)}</span>`;

function demoReplies(id, link) {
  return `<div class="demo"><span>${J.demoLabel}</span>${REPLIES.map((r) =>
    `<button type="button" data-action="reply" data-reply="${r}" data-id="${id}">${J.replies[r]}</button>`).join("")}${link
    ? `<a href="${esc(link)}" target="_blank" rel="noopener">${J.openLink}</a>` : ""}</div>`;
}

function stageAction(p, stage, d, plan, link) {
  const id = `data-id="${p.id}"`;
  switch (stage) {
    case "sent":
      return badge(T.badges.sent(T.channel[d.sent.channel], fmtDate(d.sent.date)), "sent")
        + hint(plan ? J.plan(T.channel[plan.channel], fmtDate(plan.due)) : T.badges.sentHint(NO_RESPONSE_DAYS)) + demoReplies(p.id, link);
    case "nurse_call":
      return badge(J.nurseCall, "refer")
        + `<div class="btnrow">${btn(T.actions.interested, `data-action="step" data-stage="interested" ${id}`, "btn btn--refer")}${btn(T.actions.declined, `data-action="step" data-stage="declined" ${id}`)}</div>`
        + btn(T.actions.unreachable, `data-action="step" data-stage="not_now" ${id}`, "btn btn--quiet");
    case "callback":
    case "interested":
      return (stage === "callback" ? badge(J.callback, "refer") : "")
        + `<div class="btnrow">${btn(T.actions.booked, `data-action="step" data-stage="booked" ${id}`, "btn btn--refer")}${btn(T.actions.declined, `data-action="step" data-stage="declined" ${id}`)}</div>`
        + hint(J.interestedHint);
    case "booked":
      return btn(T.actions.ldct, `data-action="step" data-stage="ldct" ${id}`, "btn btn--primary") + hint(J.bookedHint);
    case "ldct":
      return `<span class="pt__why">${T.actions.resultLabel}</span><div class="btnrow">${Object.entries(T.actions.result).map(([k, label]) =>
        btn(label, `data-action="step" data-stage="result" data-result="${k}" ${id}`)).join("")}</div>` + hint(J.ldctHint);
    case "result":
      return badge(J.result[d.result](fmtDate(nextScreening(d.result, d.journey.at(-1).date))), d.result === "negative" ? "sent" : "refer");
    case "not_now":
      return badge(J.notNow, "muted");
    case "declined":
      return badge(J.declined, "muted");
    default:
      return null;
  }
}

function action(p, bucket, d, plan, link) {
  if (d.override === "EXCLUDED") return badge(T.badges.excluded, "muted");
  const byStage = stageAction(p, stageOf(p), d, plan, link);
  if (byStage) return byStage;
  const id = `data-id="${p.id}"`;
  switch (bucket) {
    case "contact": {
      if (d.skipped) return badge(J.skipped, "muted") + btn(T.actions.unskip, `data-action="unskip" ${id}`, "btn btn--quiet");
      const { channel } = plannedContact(p);
      return `<div class="btnrow">${btn(T.actions.edit(T.channel[channel]), `data-action="open-compose" ${id}`)}${btn(T.actions.skip, `data-action="skip" ${id}`, "btn btn--quiet")}</div>` + hint(p.why || "");
    }
    case "review":
      return `<div class="btnrow">${btn(T.actions.include, `data-action="include" ${id}`)}${btn(T.actions.exclude, `data-action="exclude" ${id}`, "btn btn--danger")}</div>`;
    case "notEligible":
      return btn(T.actions.exception, `data-action="include" data-exception="1" ${id}`);
    case "waiting":
      return badge(p.why, "muted");
    default:
      return "";
  }
}

export function patientRow(p, { composing, chosenChannel, plan, link }) {
  const d = store.get(p.id);
  const bucket = bucketOf(p);
  const reason = p.reasons.filter((r) => !r.startsWith("Věk")).join(" · ");
  const flags = p.flags.filter((f) => bucket !== "notEligible" || f.sev === "warning").slice(0, 4);
  return html`<article class="pt${d.skipped && bucket === "contact" ? " pt--skipped" : ""}" id="pt-${p.id}" aria-labelledby="who-${p.id}">
    <div class="pt__row">
      ${shape(shapeOf[bucket])}
      <div style="min-width:0">
        <div class="pt__who" id="who-${p.id}">
          <strong>${p.age} ${T.years}, ${T.sex[p.sex] || ""}</strong>
          <span class="pt__id">${p.id}</span>
          <span class="pt__state">${T.buckets[bucket].label}${bucket === "notEligible" ? ` · ${T.status[p.status]}` : ""}</span>
        </div>
        <p class="pt__reason">${esc(reason)}</p>
        ${journey(stageOf(p))}
        ${flags.length ? `<ul class="flags">${flags.map((f) => `<li class="flag flag--${f.sev}">${esc(f.text)}</li>`).join("")}</ul>` : ""}
      </div>
      <div class="pt__act">${action(p, bucket, d, plan, link)}</div>
    </div>
    ${composing ? compose(p, chosenChannel) : ""}
    ${detail(p, d)}
  </article>`;
}
