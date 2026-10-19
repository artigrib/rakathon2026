// Přehled: recovered amount, promise kept rate, refinancing conversion, channels, segments, portfolios, compliance.
// Over all portfolios (the header selector picks the portfolio of the work views).
import { T, money } from "../i18n.js";
import { esc, fmtDate } from "core/util.js";
import { store } from "core/state.js";
import { CASE } from "core/case.js";
import { SEGMENTS, STRATEGY } from "../config.js";
import { groups, queueOf, recovered, remaining, stageOf } from "../domain.js";

const O = T.overview;
const STYLE = `<style>
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 0 0 24px; padding: 0; list-style: none; }
  .kpis li { border-top: 3px solid var(--ink); padding: 8px 0 0; }
  .kpis li.is-key { border-color: var(--accent); }
  .kpis b { display: block; font-size: var(--t-xl); line-height: 1.1; }
  .kpis span { display: block; color: var(--ink-2); font-size: var(--t-s); }
  .kpis small { color: var(--ink-2); }
  .comp { margin: 0; padding-left: 1.1em; }
  .comp li { margin: 0 0 6px; }
</style>`;
const section = (id, title, body) => `<section class="section grid" aria-labelledby="o-${id}">
  <div class="section__aside"><h2 id="o-${id}">${title}</h2></div><div class="section__body">${body}</div></section>`;
const table = (cols, rows, left = 1) => `<div class="tablewrap"><table><thead><tr>${cols.map((c, i) => `<th${i >= left ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const pct = (k, n) => (n ? `${Math.round((100 * k) / n)} %` : "–");
const POSITIVE = ["will_pay", "need_plan", "want_refi", "cannot_pay", "paid", "plan_chosen", "refi_accept"];
const ever = (d, stages) => (d.journey || []).some((e) => !e.ignored && stages.includes(e.stage));

export function render(ui, data) {
  const P = data.patients;
  const D = (p) => store.get(p.id);
  const totalOut = P.reduce((a, p) => a + (p.outstanding || 0), 0);
  const rec = P.reduce((a, p) => a + recovered(p), 0);
  const contacted = P.filter((p) => ever(D(p), [CASE.sent_stage]));
  const repliedP = P.filter((p) => (D(p).journey || []).some((e) => e.text));
  // promise kept rate: history of the creditor + promises resolved in the demo
  const hist = P.flatMap((p) => p.promises || []);
  const demo = P.flatMap((p) => D(p).promises || []).filter((x) => ["kept", "broken"].includes(x.status));
  const kept = hist.filter((x) => x.kept).length + demo.filter((x) => x.status === "kept").length;
  const resolved = hist.length + demo.length;
  const refiOffered = P.filter((p) => D(p).refi || ever(D(p), ["refi_offered", "refi_accepted"])).length;
  const refiAccepted = P.filter((p) => ever(D(p), ["refi_accepted"])).length;
  const stopped = P.filter((p) => ["dispute", "hardship_review", "do_not_contact", "wrong_contact"].includes(stageOf(p)) || (!stageOf(p) && (p.dispute || p.vulnerable))).length;

  const kpis = `<ul class="kpis">
    <li class="is-key"><b>${money(rec)}</b><span>${O.kpi.recovered}</span><small>${pct(rec, totalOut)}</small></li>
    <li><b>${money(totalOut)}</b><span>${O.kpi.outstanding}</span></li>
    <li><b>${pct(kept, resolved)}</b><span>${O.kpi.ptp}</span><small>${O.kpiNote.ptp(kept, resolved)}</small></li>
    <li><b>${pct(refiAccepted, refiOffered)}</b><span>${O.kpi.refi}</span><small>${O.kpiNote.refi(refiAccepted, refiOffered)}</small></li>
    <li><b>${pct(repliedP.length, contacted.length)}</b><span>${O.kpi.reached}</span><small>${O.kpiNote.reached(repliedP.length, contacted.length)}</small></li>
    <li><b>${stopped}</b><span>${O.kpi.stopped}</span><small>${O.kpiNote.stopped}</small></li>
  </ul>`;

  // channels: a reply counts for the channel of the last contact before it
  const ch = {};
  const add = (c, k) => { if (!c) return; ch[c] ||= { sent: 0, replied: 0, positive: 0 }; ch[c][k]++; };
  for (const p of P) {
    for (const h of p.history || []) { add(h.channel, "sent"); if (h.response === "replied") add(h.channel, "replied"); }
    let last = null;
    for (const e of D(p).journey || []) {
      if (e.stage === CASE.sent_stage && (!e.event || e.event === "send")) { add(e.channel, "sent"); last = e.channel; }
      else if (e.text && last) { add(last, "replied"); if (POSITIVE.includes(e.intent)) add(last, "positive"); last = null; }
    }
  }
  const chRows = Object.entries(ch).sort((a, b) => b[1].sent - a[1].sent).map(([c, v]) =>
    `<tr><td>${T.channel[c] || c}</td><td class="n">${v.sent}</td><td class="n">${v.replied}</td><td class="n">${v.positive}</td><td class="n"><b>${pct(v.replied, v.sent)}</b></td></tr>`);

  const segRows = SEGMENTS.map((s) => {
    const m = P.filter((p) => p.segment === s);
    if (!m.length) return "";
    const c = m.filter((p) => ever(D(p), [CASE.sent_stage])).length;
    const agreed = m.filter((p) => ever(D(p), ["promise_to_pay", "plan_active", "refi_accepted", "paid"])).length;
    return `<tr><td>${T.segment[s]}</td><td>${T.strategyShort[STRATEGY[s]]}</td><td class="n">${m.length}</td><td class="n">${money(m.reduce((a, p) => a + p.outstanding, 0))}</td>
      <td class="n">${c}</td><td class="n">${agreed}</td><td class="n"><b>${money(m.reduce((a, p) => a + recovered(p), 0))}</b></td></tr>`;
  }).filter(Boolean);

  const pfRows = groups(P).map((g) => {
    const m = P.filter((p) => p.portfolio === g);
    const q = (keys) => m.filter((p) => keys.includes(queueOf(p))).length;
    return `<tr tabindex="0" data-action="open-practice" data-gp="${esc(g)}"><td>${esc(g)}</td><td class="n">${m.length}</td>
      <td class="n">${money(m.reduce((a, p) => a + remaining(p), 0))}</td><td class="n">${q(["reminder", "plan", "refi"])}</td>
      <td class="n">${q(["operator", "supervisor", "human"])}</td><td class="n">${money(m.reduce((a, p) => a + recovered(p), 0))}</td></tr>`;
  });

  const C = O.comp;
  const optAll = P.filter((p) => stageOf(p) === "do_not_contact").length;
  const optCh = P.filter((p) => Array.isArray(D(p).optout) && D(p).optout.length).length;
  const comp = `<ul class="comp"><li>${C.intro}</li><li>${C.noAmount}</li><li>${C.window}</li><li>${C.cap}</li><li>${C.words}</li>
    <li>${C.optout(optAll, optCh)}</li><li>${C.stopped(P.filter((p) => ["dispute", "hardship_review"].includes(stageOf(p))).length)}</li>
    <li>${C.wrong(P.filter((p) => D(p).contactInvalid).length)}</li><li>${C.verified(P.filter((p) => D(p).verified).length)}</li></ul>`;

  return `${STYLE}<header class="pagehead"><h1>${O.title}</h1><p>${O.sub(P.length, fmtDate(data.live?.clock || data.refDate))}</p></header>${kpis}
    ${section("seg", O.segments, table(O.segCols, segRows, 2) + `<p class="note">${O.segNote}</p>`)}
    ${section("ch", O.channels, table(O.chCols, chRows) + `<p class="note">${O.chNote}</p>`)}
    ${section("pf", O.portfolios, table(O.pfCols, pfRows))}
    ${section("comp", O.compliance, comp)}`;
}
