// Registry: find any patient of the practice ("where is this person now?"). Filters = who is responsible now,
// the same buckets as the counters in Úkoly and Pro lékaře. The work queue itself is Úkoly.
import { FILTERS } from "../config.js";
import { T } from "../i18n/cs.js";
import { esc } from "../util.js";
import { ownerOf } from "../domain.js";
import { row } from "../components/row.js";

const matches = (p, q) => !q || [p.id, String(p.age), T.who(p), p.region || ""].some((s) => s.toLowerCase().includes(q));

export function patients(ui, data, rowCtx) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const clock = data.live?.clock || data.refDate;
  const owner = new Map(mine.map((p) => [p.id, ownerOf(p, clock, data.live?.plans)]));
  const q = (ui.query || "").trim().toLowerCase();
  const found = mine.filter((p) => matches(p, q));
  const inGroup = (p, f) => f === "all" || owner.get(p.id) === f || (f === "nurse" && owner.get(p.id) === "lost");
  const count = (f) => found.filter((p) => inGroup(p, f)).length;
  const list = found.filter((p) => inGroup(p, ui.filter));
  const tabs = FILTERS.map((f) => `<button type="button" data-action="pick-filter" data-filter="${f}" aria-pressed="${ui.filter === f}">
    ${T.patients.filters[f]} <span class="muted">${count(f)}</span></button>`).join("");
  return `<header class="pagehead"><h1>${T.patients.title}</h1></header>
    <label class="search"><span>${T.patients.search}</span><input type="search" id="q" value="${esc(ui.query || "")}" placeholder="${T.patients.searchHint}" autocomplete="off"></label>
    <nav class="tabs" aria-label="${T.patients.groups}">${tabs}</nav>
    <section aria-live="polite">${list.length ? list.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${T.patients.empty}</p>`}</section>`;
}
