// Košík pro sociální službu: needs from the calls, per social worker of the district, with statuses
// new → ordered (objednáno) → done (vyřízeno) and a CSV export. Above it: the seniors of the district a person has to
// deal with now (tíseň, zdravotní potíž, návštěva, smutná nálada). A summary over all districts at the end.
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { row } from "core/components/row.js";
import { esc, fmtDate } from "core/util.js";
import { alertOf, bySurname, groups, itemLabel, ITEMS, needsOf, stageDate } from "../domain.js";
import { section, tabs } from "../ui.js";

const L = T.basket;
const FILTERS = ["open", "new", "ordered", "done", "all"];
const match = { open: (n) => n.status !== "done", new: (n) => n.status === "new", ordered: (n) => n.status === "ordered", done: (n) => n.status === "done", all: () => true };

/** Basket entries of the records, newest first: {…need, p}. */
export const entries = (records) => records.flatMap((p) => needsOf(p).map((n) => ({ ...n, p })))
  .sort((a, b) => b.date.localeCompare(a.date) || bySurname(a.p, b.p));

function buttons(n) {
  const a = (status, label, kind = "") => `<button type="button" class="btn${kind ? ` btn--${kind}` : ""}" data-action="basket-status" data-id="${esc(n.p.id)}" data-need="${esc(n.id)}" data-status="${status}">${label}</button>`;
  if (n.status === "new") return a("ordered", L.order, "primary") + a("done", L.done, "link");
  if (n.status === "ordered") return a("done", L.done) + a("new", L.reopen, "link");
  return a("ordered", L.reopen, "link");
}

/** The senior's phone as a tel: link (the social worker is on a phone in the field). */
const tel = (p) => (p.phone ? `<a href="tel:${esc(p.phone.replace(/\s/g, ""))}">${esc(p.phone)}</a>` : "");

export function render(ui, data, rowCtx) {
  const mine = mineOf(data, ui);
  const alerts = mine.filter((p) => alertOf(p)).sort((a, b) => stageDate(a).localeCompare(stageDate(b)) || bySurname(a, b));
  const alertRows = alerts.map((p) => row(p, rowCtx.of(p))).join("");
  const all = entries(mine);
  const filter = FILTERS.includes(ui.basketFilter) ? ui.basketFilter : "open";
  const counts = Object.fromEntries(FILTERS.map((f) => [f, all.filter(match[f]).length]));
  const list = all.filter(match[filter]);

  const byWorker = new Map();
  for (const n of list) byWorker.set(n.p.worker, [...(byWorker.get(n.p.worker) || []), n]);
  const workers = [...byWorker.entries()].sort((a, b) => a[0].localeCompare(b[0], "cs")).map(([w, ns]) =>
    section(`w-${w.replace(/\W+/g, "")}`, ns.length, esc(w), ns.map((n) => `<div class="sn-need">
      <div><button type="button" class="who" data-action="open-card" data-id="${esc(n.p.id)}">${esc(n.p.name)}</button>
        <div><b>${esc(itemLabel(n.item))}</b> <span class="sn-status is-${n.status}">${L.status[n.status]}</span></div>
        <span class="sn-muted">${esc(n.p.address)} · ${fmtDate(n.date)}</span>
        <span class="sn-muted">${tel(n.p)}${n.p.phone && n.p.worker ? " · " : ""}${esc(n.p.worker || "")}</span></div>
      <div class="actions">${buttons(n)}</div></div>`).join(""), { hint: L.workerSub(ns.length) })).join("");

  const sum = Object.keys(ITEMS).map((k) => [k, ...["new", "ordered", "done"].map((s) => all.filter((n) => n.item === k && n.status === s).length)])
    .filter(([, a, b, c]) => a + b + c);
  const summary = sum.length ? `<div class="tablewrap"><table><thead><tr>${L.sumCols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead>
    <tbody>${sum.map(([k, a, b, c]) => `<tr><td>${esc(itemLabel(k))}</td><td class="n"><b>${a}</b></td><td class="n">${b}</td><td class="n">${c}</td></tr>`).join("")}</tbody></table></div>` : `<p class="empty">${L.empty}</p>`;

  const dists = groups(data.patients).map((g) => {
    const recs = data.patients.filter((p) => p.district === g);
    const es = entries(recs);
    return `<tr tabindex="0" data-action="pick-district" data-gp="${esc(g)}"${g === ui.gp ? ' aria-current="true"' : ""}><td>${esc(g)}</td><td class="n">${recs.length}</td>
      <td class="n">${es.filter(match.open).length}</td><td class="n"><b>${es.filter(match.new).length}</b></td></tr>`;
  }).join("");
  const districts = `<div class="tablewrap"><table><thead><tr>${L.distCols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead><tbody>${dists}</tbody></table></div>`;

  return `<header class="pagehead"><h1>${L.title}</h1><p>${L.sub(esc(ui.gp || ""), counts.open)}</p></header>
    ${section("alerts", alerts.length, L.alerts.title, alertRows || `<p class="empty">${L.alerts.empty}</p>`, { due: true, hint: L.alerts.hint, cls: alerts.length ? " section--lost" : "" })}
    <div class="sn-toolbar">${tabs("basket-filter", FILTERS, L.filters, filter, counts)}
      <button type="button" class="btn" data-action="basket-csv">${L.csv}</button></div>
    <div class="sn-basket">${workers || `<p class="empty">${L.empty}</p>`}</div>
    ${section("sum", "", L.summary, summary)}
    ${section("districts", "", L.districts, districts, { cls: " section--quiet" })}`;
}

export const badge = (mine) => entries(mine).filter((n) => n.status === "new").length;
