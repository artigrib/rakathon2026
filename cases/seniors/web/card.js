// Blocks of the senior's card (core/components/card.js): who it is, mood of 30 days and open needs before the journey;
// the relative and the history of calls after the communication.
import { T } from "./i18n.js";
import { esc, fmtDate } from "core/util.js";
import { dialogue, recapLine } from "core/components/comm.js";
import { callsOf, itemLabel, moodSeries, openNeeds } from "./domain.js";
import { chips, moodBadge, sparkline } from "./ui.js";

const C = T.card;

function facts(p) {
  const s = p.schedule;
  const rows = [
    [C.age, `${p.age} let`],
    [C.address, p.address],
    [C.phone, p.phone],
    [C.alone, p.alone ? C.aloneYes(p) : ""],
    [C.mobility, T.mobility[p.mobility] || p.mobility],
    [C.schedule, s ? `${T.schedule[s.kind] || T.schedule.days(s.days)}, ${T.schedule.window(s)}, ${T.channel[p.channel] || p.channel}` : ""],
    [C.worker, p.worker],
    [C.since, fmtDate(p.since)],
  ].filter(([, v]) => v);
  return `<dl class="kv kv--wide">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
}

function mood(p) {
  const pts = moodSeries(p);
  const avg = pts.length ? (pts.reduce((s, x) => s + x.mood, 0) / pts.length).toFixed(1).replace(".", ",") : "";
  return `${sparkline(pts)}${avg ? `<p class="sn-muted">${C.moodAvg(avg)}, ${T.mood[pts.at(-1).mood]} ${fmtDate(pts.at(-1).date)}</p>` : ""}`;
}

function history(p) {
  const calls = callsOf(p);
  const li = (c) => {
    const what = c.relative ? C.relativeSms : !c.answered ? (p.sex === "F" ? C.noAnswerF : C.noAnswer)
      : [T.intent[c.intent], (c.items || []).map(itemLabel).join(", ")].filter(Boolean).join(": ");
    return `<li><time>${fmtDate(c.date)}${c.time ? ` ${c.time}` : ""}</time><div>${c.answered ? moodBadge(c.mood) : ""} ${esc(what)}${c.live ? ` <span class="sn-tag">${T.calls.live}</span>` : ""}
      ${c.text ? `<q>${esc(c.text)}</q>` : ""}${c.note ? `<span class="sn-muted">${esc(c.note)}</span>` : ""}${recapLine(c.summary, c.confirmed)}${dialogue(c.transcript)}</div></li>`;
  };
  const head = calls.slice(0, 8), rest = calls.slice(8);
  return `<ol class="sn-hist">${head.map(li).join("")}</ol>
    ${rest.length ? `<details class="card__more"><summary>${C.more(rest.length)}</summary><ol class="sn-hist">${rest.map(li).join("")}</ol></details>` : ""}`;
}

function relative(p) {
  const r = p.relative;
  if (!r) return "";
  return `<dl class="kv kv--wide"><dt>${esc(r.rel)}</dt><dd>${esc(r.name)}</dd>
    <dt>${C.phone}</dt><dd><a href="tel:${esc(r.phone.replace(/\s/g, ""))}">${esc(r.phone)}</a></dd></dl>`;
}

export function blocks(p) {
  const needs = openNeeds(p);
  return {
    before: `<section class="card__block"><h3>${C.facts}</h3>${facts(p)}</section>
      <section class="card__block"><h3>${C.mood}</h3>${mood(p)}</section>
      <section class="card__block"><h3>${C.needs}</h3>${needs.length ? chips(needs) : `<p class="sn-muted">${C.needsNone}</p>`}</section>`,
    after: `<section class="card__block"><h3>${C.relative}</h3>${relative(p)}</section>
      <section class="card__block"><h3>${C.calls}</h3>${history(p)}</section>
      <p class="sn-muted">${esc(p.id)}, ${esc(p.district)}</p>`,
  };
}
