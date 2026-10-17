// Patient card: one patient, one panel (side drawer on desktop, full screen on a phone). Top to bottom, one idea per block:
// who and what now (with the one next action), why eligible, journey, all communication, contacts, records.
import { T } from "../i18n/cs.js";
import { esc, fmtDate } from "../util.js";
import { stageOf } from "../domain.js";
import { store } from "../state.js";
import { journey } from "./journey.js";
import { comm } from "./comm.js";
import { compose } from "./compose.js";
import { actions, describe } from "./row.js";

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

export function card(p, { plan, outbox, composing, chosenChannel, owner, lost }) {
  const d = store.get(p.id);
  const { title, sub } = describe(p, d, plan);
  const warnings = p.flags.filter((f) => f.sev === "warning");
  const path = journey(stageOf(p));
  const why = lost ? T.lost[lost.code](lost.days, p) : "";
  return `<div class="card-wrap" data-action="close-card">
    <section class="card" role="dialog" aria-modal="true" aria-labelledby="card-title" data-stop>
      <header class="card__head">
        <div>
          <h2 id="card-title" tabindex="-1">${esc(T.who(p))}</h2>
          ${owner ? `<p class="card__owner">${C.owner[owner]}</p>` : ""}
        </div>
        <button type="button" class="card__close" data-action="close-card" aria-label="${C.close}">✕</button>
      </header>
      <div class="card__now">
        ${why ? `<em class="lostwhy">${esc(why)}</em>` : ""}
        <b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}
        <div class="actions">${actions(p, d)}</div>
        ${composing ? compose(p, chosenChannel) : ""}
      </div>
      ${warnings.length ? `<ul class="warn">${warnings.map((f) => `<li>${esc(f.text)}</li>`).join("")}</ul>` : ""}
      <section class="card__block"><h3>${C.why}</h3>${facts(p)}</section>
      ${path ? `<section class="card__block"><h3>${D.journey}</h3>${path}</section>` : ""}
      <section class="card__block"><h3>${T.comm.title}</h3>${comm(p, d, plan, outbox)}</section>
      <section class="card__block"><h3>${D.contacts}</h3>${contacts(p)}</section>
      ${records(p)}
    </section>
  </div>`;
}
