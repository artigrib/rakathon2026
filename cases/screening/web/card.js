// Screening blocks of the patient card (core/components/card.js): why eligible (smoking, CT) before the journey,
// contacts and the engine's records after the communication.
import { T } from "./i18n.js";
import { esc, fmtDate } from "core/util.js";

const D = T.detail;
const C = T.card;

function facts(p) {
  const s = p.smoking;
  const chest = [...(p.ct || [])].filter((c) => c.region === "chest").sort((a, b) => (b.date || "").localeCompare(a.date || ""))[0];
  const rows = [
    [C.age, `${p.age} let`],
    [D.smoking, s ? `${D.smokingStatus[s.status] || D.unknown}${s.quitYear ? `, ${D.quit(s.quitYear)}` : ""}` : D.noSmoking],
    [D.packYears, s?.packYears != null ? `${s.packYears}${D.pySource[s.source] ? ` (${D.pySource[s.source]})` : ""}` : D.unknown],
    [C.lastCt, chest ? `${fmtDate(chest.date)}, ${D.ctProtocol[chest.protocol] || chest.protocol}, ${D.ctStatus[chest.status]}` : D.noCt],
  ];
  return `<dl class="kv kv--wide">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
}

function contacts(p) {
  const rows = [];
  if (p.phone) rows.push(`<dt>${D.phone}</dt><dd><a href="tel:${esc(p.phone.replace(/\s/g, ""))}">${esc(p.phone)}</a></dd>`);
  rows.push(`<dt>${D.portal}</dt><dd>${p.portal ? D.portalYes : D.portalNo}</dd>`);
  rows.push(`<dt>${D.prefers}</dt><dd>${esc(T.channel[p.pref] || p.pref || D.unknown)}</dd>`);
  if (p.pneu) rows.push(`<dt>${D.pneumologist}</dt><dd>${esc(p.pneu)}</dd>`);
  return `<dl class="kv kv--wide">${rows.join("")}</dl>`;
}

function records(p) {
  const ct = (p.ct || []).map((c) => `<li><time>${fmtDate(c.date)}</time><span>${esc(D.ctProtocol[c.protocol] || c.protocol)}, ${esc(D.ctStatus[c.status])}${c.external ? `, ${D.external}` : ""}${c.report ? `. ${esc(c.report)}` : ""}</span></li>`).join("");
  return `<details class="card__more"><summary>${C.more}</summary>
    <h3>${D.evaluation}</h3><ul class="plain">${p.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    ${p.smoking?.note ? `<h3>${D.note}</h3><p>${esc(p.smoking.note)}</p>` : ""}
    <h3>${D.ct}</h3>${ct ? `<ul class="timeline">${ct}</ul>` : `<p>${D.noCt}</p>`}
    <p class="muted">${p.id}${p.region ? `, ${esc(p.region)}` : ""}</p>
  </details>`;
}

export function blocks(p) {
  return {
    before: `<section class="card__block"><h3>${C.why}</h3>${facts(p)}</section>`,
    after: `<section class="card__block"><h3>${D.contacts}</h3>${contacts(p)}</section>
      ${records(p)}`,
  };
}
