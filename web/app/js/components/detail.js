import { T } from "../i18n/cs.js";
import { esc, fmtDate, html } from "../util.js";
import { stageOf } from "../domain.js";
import { journey } from "./journey.js";
import { comm } from "./comm.js";

const D = T.detail;

function smoking(s) {
  if (!s) return `<p>${D.noSmoking}</p>`;
  const src = D.pySource[s.source];
  return html`<dl class="kv">
    <dt>${D.status}</dt><dd>${D.smokingStatus[s.status] || D.unknown}${s.quitYear ? `, ${D.quit(s.quitYear)}` : ""}</dd>
    <dt>${D.packYears}</dt><dd>${s.packYears ?? D.unknown}${src ? ` <span class="muted">(${src})</span>` : ""}</dd>
    <dt>${D.note}</dt><dd>${esc(s.note || D.unknown)}</dd>
  </dl>`;
}

function ct(list) {
  if (!list.length) return `<p>${D.noCt}</p>`;
  return html`<ul class="timeline">${list.map((c) => html`<li><time>${fmtDate(c.date)}</time><span>
    ${D.ctProtocol[c.protocol] || c.protocol}, ${D.ctStatus[c.status]}${c.external ? `, ${D.external}` : ""}${c.report ? `. ${esc(c.report)}` : ""}
  </span></li>`)}</ul>`;
}

function contacts(p) {
  const tel = p.phone ? `<dt>${D.phone}</dt><dd><a href="tel:${esc(p.phone.replace(/\s/g, ""))}">${esc(p.phone)}</a></dd>` : "";
  return html`<dl class="kv">${tel}
      <dt>${D.portal}</dt><dd>${p.portal ? D.portalYes : D.portalNo}</dd>
      <dt>${D.prefers}</dt><dd>${T.channel[p.pref] || p.pref || D.unknown}</dd>
      ${p.pneu ? `<dt>${D.pneumologist}</dt><dd>${p.pneu}</dd>` : ""}
    </dl>`;
}

export function detail(p, decision, { plan = null, outbox = null } = {}) {
  const warnings = p.flags.filter((f) => f.sev === "warning");
  const info = p.flags.filter((f) => f.sev !== "warning");
  const path = journey(stageOf(p));
  return html`<div class="detail">
    <section class="detail__comm"><h3>${T.comm.title}</h3>${comm(p, decision, plan, outbox)}</section>
    <section><h3>${D.evaluation} <span class="muted" style="font-weight:400">${p.id}</span></h3><ul class="timeline">${p.reasons.map((r) => `<li style="grid-template-columns:1fr">${esc(r)}</li>`)}${
      info.map((f) => `<li style="grid-template-columns:1fr" class="muted">${esc(f.text)}</li>`)}</ul>
      ${warnings.length ? html`<h3 style="margin-top:16px">${D.warnings}</h3><ul class="warn">${warnings.map((f) => `<li>${esc(f.text)}</li>`)}</ul>` : ""}</section>
    ${path ? html`<section><h3>${D.journey}</h3>${path}</section>` : ""}
    <section><h3>${D.contacts}</h3>${contacts(p)}</section>
    <section><h3>${D.smoking}</h3>${smoking(p.smoking)}</section>
    <section><h3>${D.ct}</h3>${ct(p.ct)}</section>
  </div>`;
}
