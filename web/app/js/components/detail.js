import { T } from "../i18n/cs.js";
import { esc, fmtDate, html } from "../util.js";
import { stageOf } from "../domain.js";
import { journey } from "./journey.js";

const D = T.detail;

function smoking(s) {
  if (!s) return `<p>${D.noSmoking}</p>`;
  const src = D.pySource[s.source];
  return html`<dl class="kv">
    <dt>${D.status}</dt><dd>${D.smokingStatus[s.status] || "—"}${s.quitYear ? `, ${D.quit(s.quitYear)}` : ""}</dd>
    <dt>${D.packYears}</dt><dd>${s.packYears ?? "—"}${src ? ` <span class="muted">(${src})</span>` : ""}</dd>
    <dt>${D.note}</dt><dd>${esc(s.note || "—")}</dd>
  </dl>`;
}

function ct(list) {
  if (!list.length) return `<p>${D.noCt}</p>`;
  return html`<ul class="timeline">${list.map((c) => html`<li><time>${fmtDate(c.date)}</time><span>
    ${D.ctProtocol[c.protocol] || c.protocol}, ${D.ctStatus[c.status]}${c.external ? `, ${D.external}` : ""}${c.report ? `. ${esc(c.report)}` : ""}
  </span></li>`)}</ul>`;
}

function contacts(p, decision) {
  const rows = p.history.map((h) => html`<li><time>${fmtDate(h.date)}</time><span>
    ${T.channel[h.channel] || h.channel}: ${D.msgType[h.type] || h.type}, ${D.delivery[h.delivery]}${h.response ? `, ${D.response[h.response]}` : ""}
  </span></li>`);
  for (const e of decision.journey || []) {
    const text = !e.stage ? `${T.channel[e.channel] || e.channel}: ${D.delivery[e.delivery] || e.delivery}`
      : e.stage === "sent" ? (e.auto ? D.sentAuto(T.channel[e.channel], e.step) : D.sentByPractice(T.channel[e.channel]))
      : D.event[e.stage] + (e.result ? `: ${T.actions.result[e.result].toLowerCase()}` : "");
    const said = e.text && e.stage !== "sent" ? `<br><span class="muted">${esc(D.said(e.text))}${e.source === "ai" ? ` – ${esc(D.byAi(e.why, e.when))}` : ""}</span>` : "";
    rows.push(`<li><time>${fmtDate(e.date)}</time><span>${esc(text)}${said}</span></li>`);
  }
  return html`${rows.length ? `<ul class="timeline">${rows.join("")}</ul>` : `<p>${D.noContacts}</p>`}
    <dl class="kv" style="margin-top:10px">
      <dt>${D.portal}</dt><dd>${p.portal ? D.portalYes : D.portalNo}</dd>
      <dt>${D.prefers}</dt><dd>${T.channel[p.pref] || p.pref || "—"}</dd>
      ${p.pneu ? `<dt>${D.pneumologist}</dt><dd>${p.pneu}</dd>` : ""}
    </dl>`;
}

export function detail(p, decision) {
  const warnings = p.flags.filter((f) => f.sev === "warning");
  const info = p.flags.filter((f) => f.sev !== "warning");
  const path = journey(stageOf(p));
  return html`<div class="detail">
    <section><h3>${D.evaluation}</h3><ul class="timeline">${p.reasons.map((r) => `<li style="grid-template-columns:1fr">${esc(r)}</li>`)}${
      info.map((f) => `<li style="grid-template-columns:1fr" class="muted">${esc(f.text)}</li>`)}</ul>
      ${warnings.length ? html`<h3 style="margin-top:16px">${D.warnings}</h3><ul class="warn">${warnings.map((f) => `<li>${esc(f.text)}</li>`)}</ul>` : ""}</section>
    ${path ? html`<section><h3>${D.journey}</h3>${path}</section>` : ""}
    <section><h3>${D.contacts}</h3>${contacts(p, decision)}</section>
    <section><h3>${D.smoking}</h3>${smoking(p.smoking)}</section>
    <section><h3>${D.ct}</h3>${ct(p.ct)}</section>
  </div>`;
}
