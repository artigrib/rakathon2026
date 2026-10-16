// Every patient of the practice, filtered by phase. Same row as in the task list.
import { FILTERS } from "../config.js";
import { T } from "../i18n/cs.js";
import { countBy } from "../util.js";
import { phaseOf } from "../domain.js";
import { row } from "../components/row.js";

export function patients(ui, data, rowCtx) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const counts = { all: mine.length, ...countBy(mine, phaseOf) };
  const list = ui.filter === "all" ? mine : mine.filter((p) => phaseOf(p) === ui.filter);
  const tabs = FILTERS.map((f) => `<button type="button" data-action="pick-filter" data-filter="${f}" aria-pressed="${ui.filter === f}">
    ${T.patients.filters[f]} <span class="muted">${counts[f] || 0}</span></button>`).join("");
  return `<header class="pagehead"><h1>${T.patients.title}</h1></header>
    <nav class="tabs" aria-label="Skupiny pacientů">${tabs}</nav>
    <section aria-live="polite">${list.length ? list.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${T.patients.empty}</p>`}</section>`;
}
