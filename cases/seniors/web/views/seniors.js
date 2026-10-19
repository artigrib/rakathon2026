// Kartotéka seniorů: one tile per senior (state, mood of 30 days, open needs). Click opens the card.
// Tabs = who acts now (domain.ownerOf), the same buckets as the counters elsewhere.
import { T } from "../i18n.js";
import { cfg, mineOf } from "core/case.js";
import { esc } from "core/util.js";
import { store } from "core/state.js";
import { alertOf, moodSeries, openNeeds, ownerOf } from "../domain.js";
import { stateLine } from "../row.js";
import { chips, sparkline, tabs } from "../ui.js";

const L = T.seniors;
const text = (p) => [p.id, p.name, p.address, p.relative?.name, p.worker].join(" ").toLowerCase();

function tile(p, owner, plan) {
  const { title, sub } = stateLine(p, store.get(p.id), plan);
  const alert = alertOf(p) || owner === "lost";
  return `<article class="sn-tile${alert ? " is-alert" : ""}" id="pt-${esc(p.id)}">
    <button type="button" class="who" data-action="open-card" data-id="${esc(p.id)}" aria-haspopup="dialog">${esc(T.who(p))}</button>
    <span class="muted">${esc(p.address)} · ${esc(T.mobility[p.mobility] || "")}</span>
    <b class="sn-state">${esc(title)}</b>${sub ? `<span class="muted">${esc(sub)}</span>` : ""}
    ${sparkline(moodSeries(p))}
    ${chips(openNeeds(p))}
  </article>`;
}

export function render(ui, data) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const plans = data.live?.plans;
  const owner = new Map(mine.map((p) => [p.id, ownerOf(p, clock, plans)]));
  const q = (ui.query || "").trim().toLowerCase();
  const found = mine.filter((p) => !q || text(p).includes(q));
  const inGroup = (p, f) => f === "all" || owner.get(p.id) === f || (f === "operator" && owner.get(p.id) === "lost");
  const filter = cfg.FILTERS.includes(ui.filter) ? ui.filter : "all";
  const counts = Object.fromEntries(cfg.FILTERS.map((f) => [f, found.filter((p) => inGroup(p, f)).length]));
  const list = found.filter((p) => inGroup(p, filter)).sort((a, b) => a.name.localeCompare(b.name, "cs"));
  return `<header class="pagehead"><h1>${L.title}</h1></header>
    <label class="search"><span>${L.search}</span><input type="search" id="q" value="${esc(ui.query || "")}" placeholder="${L.searchHint}" autocomplete="off"></label>
    ${tabs("pick-filter", cfg.FILTERS, L.filters, filter, counts)}
    <section aria-live="polite">${list.length ? `<div class="sn-grid">${list.map((p) => tile(p, owner.get(p.id), plans?.[p.id])).join("")}</div>` : `<p class="empty">${L.empty}</p>`}</section>`;
}
