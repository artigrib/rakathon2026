import { T } from "../i18n/cs.js";
import { esc, fmtDate, html } from "../util.js";

const D = T.detail;

function smoking(s) {
  if (!s) return `<p>${D.noSmoking}</p>`;
  const src = D.pySource[s.source];
  return html`<dl class="kv">
    <dt>${D.status}</dt><dd>${D.smokingStatus[s.status] || "—"}${s.quitYear ? `, ${D.quit(s.quitYear)}` : ""}</dd>
    <dt>${D.packYears}</dt><dd class="num">${s.packYears ?? "—"}${src ? ` <span class="pt__why">(${src})</span>` : ""}</dd>
    <dt>${D.note}</dt><dd>${esc(s.note || "—")}</dd>
  </dl>`;
}

function ct(list) {
  if (!list.length) return `<p>${D.noCt}</p>`;
  return html`<ul class="timeline">${list.map((c) => html`<li><time>${fmtDate(c.date)}</time><span>
    ${D.ctProtocol[c.protocol] || c.protocol} · ${D.ctStatus[c.status]}${c.external ? ` · ${D.external}` : ""}${c.report ? ` · ${esc(c.report)}` : ""}
  </span></li>`)}</ul>`;
}

function contacts(p, decision) {
  const rows = p.history.map((h) => html`<li><time>${fmtDate(h.date)}</time><span>
    ${T.channel[h.channel] || h.channel}: ${D.msgType[h.type] || h.type} · ${D.delivery[h.delivery]}${h.response ? ` · ${D.response[h.response]}` : ""}
  </span></li>`);
  for (const e of decision.journey || []) {
    const text = !e.stage ? `${T.channel[e.channel] || e.channel}: ${D.delivery[e.delivery] || e.delivery}`
      : e.stage === "sent" ? (e.auto ? D.sentAuto(T.channel[e.channel], e.step) : D.sentByDoctor(T.channel[e.channel]))
      : D.event[e.stage] + (e.result ? ` · ${T.actions.result[e.result]}` : "");
    const said = e.text && e.stage !== "sent" ? ` <span class="pt__why">${esc(T.journey.said(e.text))}${
      e.source === "ai" ? ` · ${esc(D.byAi(e.why, e.when))}` : ""}</span>` : "";
    rows.push(`<li><time>${fmtDate(e.date)}</time><span><strong>${esc(text)}</strong>${said}</span></li>`);
  }
  return html`${rows.length ? `<ul class="timeline">${rows.join("")}</ul>` : `<p>${D.noContacts}</p>`}
    <dl class="kv" style="margin-top:10px">
      <dt>${D.portal}</dt><dd>${p.portal ? D.portalYes : D.portalNo}</dd>
      <dt>${D.prefers}</dt><dd>${T.channel[p.pref] || p.pref || "—"}</dd>
      ${p.pneu ? `<dt>${D.pneumologist}</dt><dd class="mono">${p.pneu}</dd>` : ""}
    </dl>`;
}

export function detail(p, decision) {
  return html`<details class="more">
    <summary>${T.actions.details}</summary>
    <div class="detail">
      <section><h3>${D.evaluation}</h3><ul class="timeline">${p.reasons.map((r) => `<li style="grid-template-columns:1fr">${esc(r)}</li>`)}</ul></section>
      <section><h3>${D.smoking}</h3>${smoking(p.smoking)}</section>
      <section><h3>${D.ct}</h3>${ct(p.ct)}</section>
      <section><h3>${D.contacts}</h3>${contacts(p, decision)}</section>
    </div>
  </details>`;
}
