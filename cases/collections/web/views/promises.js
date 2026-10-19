// Sliby a splátky: promise-to-pay tracker and instalment plans, kept and broken.
import { T, money } from "../i18n.js";
import { mineOf } from "core/case.js";
import { esc, fmtDate } from "core/util.js";
import { store } from "core/state.js";
import { daysBetween } from "../domain.js";
import { SEGMENTS } from "../config.js";

const V = T.promisesView;
const STYLE = `<style>
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 0 0 24px; padding: 0; list-style: none; }
  .kpis li { border-top: 3px solid var(--ink); padding: 8px 0 0; }
  .kpis b { display: block; font-size: var(--t-xl); line-height: 1.1; }
  .kpis span { color: var(--ink-2); font-size: var(--t-s); }
  .st-kept, .st-paid { color: var(--accent); font-weight: 600; }
  .st-broken, .st-missed { color: var(--warn); font-weight: 600; }
  td.nm { white-space: nowrap; font-weight: 600; }
  tr[data-action] { cursor: pointer; }
</style>`;

const section = (id, title, body) => `<section class="section grid" aria-labelledby="pr-${id}">
  <div class="section__aside"><h2 id="pr-${id}">${title}</h2></div><div class="section__body">${body}</div></section>`;
const table = (cols, rows) => `<div class="tablewrap"><table><thead><tr>${cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead>
  <tbody>${rows.join("")}</tbody></table></div>`;
const st = (s) => `<span class="st-${s}">${V.status[s] || s}</span>`;
const open = (p) => `tabindex="0" data-action="open-card" data-id="${p.id}"`;

export function render(ui, data) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const all = mine.flatMap((p) => (store.get(p.id).promises || []).map((x) => ({ p, x })));
  const openP = all.filter(({ x }) => x.status === "open").sort((a, b) => a.x.date.localeCompare(b.x.date));
  const doneP = all.filter(({ x }) => ["kept", "broken"].includes(x.status)).sort((a, b) => b.x.date.localeCompare(a.x.date));
  const kept = doneP.filter(({ x }) => x.status === "kept").length;
  const plans = mine.filter((p) => store.get(p.id).plan?.items?.length).map((p) => ({ p, pl: store.get(p.id).plan, stage: store.get(p.id).stage }));
  const hist = mine.flatMap((p) => p.promises || []);
  const histKept = hist.filter((x) => x.kept).length;
  const rate = (k, n) => (n ? `${Math.round((100 * k) / n)} %` : "–");

  const kpis = `<ul class="kpis">
    <li><b>${openP.length}</b><span>${V.kpi.open}</span></li>
    <li><b>${money(openP.reduce((a, { x }) => a + (+x.amount || 0), 0))}</b><span>${V.kpi.promised}</span></li>
    <li><b>${kept}</b><span>${V.kpi.kept}</span></li>
    <li><b>${doneP.length - kept}</b><span>${V.kpi.broken}</span></li>
    <li><b>${rate(kept + histKept, doneP.length + hist.length)}</b><span>${V.kpi.rate}</span></li>
    <li><b>${plans.filter((x) => x.stage === "plan_active").length}</b><span>${V.kpi.plans}</span></li>
  </ul>`;

  const C = V.cols;
  const openRows = openP.map(({ p, x }) => {
    const left = daysBetween(clock, x.date);
    return `<tr ${open(p)}><td class="nm">${esc(p.name)}</td><td class="n">${money(x.amount)}</td>
      <td class="n">${fmtDate(x.date)}<br><small class="muted">${left < 0 ? V.overdue(-left) : V.inDays(left)}${x.dateGiven === false ? `, ${V.noDate}` : ""}</small></td>
      <td class="n">${fmtDate(x.made)}</td><td class="n">${esc(T.state.via[x.via] || x.via || "")}</td><td class="n">${st(x.status)}</td></tr>`;
  });
  const planRows = plans.map(({ p, pl, stage }) => {
    const paid = pl.items.filter((i) => i.status === "paid");
    const next = pl.items.find((i) => i.status === "open");
    const missed = pl.items.some((i) => i.status === "missed");
    return `<tr ${open(p)}><td class="nm">${esc(p.name)}</td><td class="n">${pl.kind === "deferral" ? V.deferral : V.planOf(pl.n, money(pl.monthly))}</td>
      <td class="n">${paid.length} / ${pl.items.length}, ${money(paid.reduce((a, i) => a + i.amount, 0))}</td>
      <td class="n">${next ? `${fmtDate(next.due)}, ${money(next.amount)}` : "–"}</td>
      <td class="n">${missed ? st("missed") : stage === "paid" ? st("paid") : st("open")}</td></tr>`;
  });
  const doneRows = doneP.slice(0, 30).map(({ p, x }) => `<tr ${open(p)}><td class="nm">${esc(p.name)}</td><td class="n">${money(x.amount)}</td>
      <td class="n">${fmtDate(x.date)}</td><td class="n">${fmtDate(x.made)}</td><td class="n">${esc(T.state.via[x.via] || x.via || "")}</td><td class="n">${st(x.status)}</td></tr>`);

  const bySeg = SEGMENTS.map((s) => {
    const ps = mine.filter((p) => p.segment === s).flatMap((p) => p.promises || []);
    const k = ps.filter((x) => x.kept).length;
    return ps.length ? `<tr><td>${T.segment[s]}</td><td class="n">${ps.length}</td><td class="n">${k}</td><td class="n"><b>${rate(k, ps.length)}</b></td></tr>` : "";
  }).filter(Boolean);

  return `${STYLE}<header class="pagehead"><h1>${V.title}</h1><p>${V.sub}</p></header>${kpis}
    ${section("open", V.open, openRows.length ? table([C.who, C.amount, C.date, C.made, C.via, C.status], openRows) : `<p class="empty">${V.openEmpty}</p>`)}
    ${section("plans", V.plans, planRows.length ? table([C.who, C.plan, C.paid, C.next, C.status], planRows) : `<p class="empty">${V.plansEmpty}</p>`)}
    ${section("done", V.done, doneRows.length ? table([C.who, C.amount, C.date, C.made, C.via, C.status], doneRows) : `<p class="empty">${V.doneEmpty}</p>`)}
    ${section("hist", V.history, (bySeg.length ? table([C.segment, C.n, C.kept, C.rate], bySeg) : "") + `<p class="note">${V.historyNote}</p>`)}`;
}

export const badge = (mine, clock) => mine.filter((p) => (store.get(p.id).promises || []).some((x) => x.status === "open" && x.date < clock)).length;
