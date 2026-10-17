// The doctor's screen: only what the doctor decides or signs, once a week, nothing else.
// (Mentor: simplicity for GPs, who are often older; the doctor decides exceptions.)
import { T } from "../i18n/cs.js";
import { addDays, lostOf, ownerOf, stageOf, taskOf } from "../domain.js";
import { row } from "../components/row.js";
import { store } from "../state.js";
import { esc, fmtDate } from "../util.js";

const L = T.doctor;

const section = (id, count, title, body, due = false) => `<section class="section grid" aria-labelledby="d-${id}">
  <div class="section__aside"><span class="count${due && count ? " is-due" : ""}">${count}</span><h2 id="d-${id}">${title}</h2></div>
  <div class="section__body">${body}</div></section>`;

/** Patients that the doctor has to decide on now (shown as a count in the navigation). */
export const doctorCount = (mine, clock, plans) => mine.filter((p) => ownerOf(p, clock, plans) === "doctor").length;

export function doctor(ui, data, rowCtx) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const clock = data.live?.clock || data.refDate;
  const weekAgo = addDays(clock, -7);

  const decide = mine.filter((p) => taskOf(p) === "doctor");
  const results = mine.filter((p) => stageOf(p) === "result" && store.get(p.id).result !== "negative" && !store.get(p.id).resultAck);

  // Codes to report this week: 01196 = referred to the pneumologist, 01197 = the patient refuses (second refusal).
  const coded = (stage) => mine.flatMap((p) => (store.get(p.id).journey || [])
    .filter((e) => e.stage === stage && !e.ignored && e.date >= weekAgo && e.date <= clock)
    .filter((e) => (stage === "booked" ? e.via === "ui" && !e.text : e.intent !== "opt_out")).map((e) => ({ p, date: e.date })));
  const c96 = coded("booked"), c97 = coded("declined");
  const codeList = (items) => items.length
    ? `<ul class="codes">${items.map(({ p, date }) => `<li><span>${esc(T.who(p))}, ${esc(p.id)}</span><time>${fmtDate(date)}</time></li>`).join("")}</ul>` : "";
  const codes = `<dl class="kv kv--codes">
      <dt>${L.c96}</dt><dd><b>${c96.length}</b>${codeList(c96)}</dd>
      <dt>${L.c97}</dt><dd><b>${c97.length}</b>${codeList(c97)}</dd>
    </dl>`;

  const lost = mine.filter((p) => lostOf(p, clock, data.live?.plans));
  const reached = (s) => mine.filter((p) => (store.get(p.id).journey || []).some((e) => s.includes(e.stage) && !e.ignored)).length;
  const stats = [[L.eligible, mine.filter((p) => p.status === "ELIGIBLE" || store.get(p.id).override === "ELIGIBLE").length],
    [L.invited, reached(["sent"])], [L.replied, reached(["interested", "callback", "booked"])], [L.referred, reached(["booked"])],
    [L.ldct, reached(["ldct", "result"])], [L.lost, lost.length]];
  const funnel = `<ul class="stats">${stats.map(([k, v], i) => `<li class="${i === 5 && v ? "is-lost" : ""}"><div>${k}</div><b>${v}</b></li>`).join("")}</ul>`;

  return `<header class="pagehead"><h1>${L.title}</h1><p>${L.sub(fmtDate(weekAgo), fmtDate(clock))}</p></header>
    ${section("decide", decide.length, L.decide, decide.length ? decide.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${L.none}</p>`, true)}
    ${section("results", results.length, L.results, results.length ? results.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${L.none}</p>`, true)}
    ${section("codes", c96.length + c97.length, L.codes, codes)}
    ${section("programme", "", L.programme, funnel)}`;
}

