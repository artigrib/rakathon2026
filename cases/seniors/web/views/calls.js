// Kartotéka hovorů: every call of the district, newest first, with what the senior said, mood and the needs the system
// recognised. Calls and answers of the demo are marked.
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { esc, fmtDate } from "core/util.js";
import { addDays, callsOf, itemLabel } from "../domain.js";
import { moodBadge, tabs } from "../ui.js";

const L = T.calls;
const FILTERS = ["all", "noanswer", "needs", "mood", "health"];
const match = {
  all: () => true,
  noanswer: (c) => !c.answered && !c.relative,
  needs: (c) => c.items?.length > 0,
  mood: (c) => c.intent === "low_mood" || (c.mood && c.mood <= 2),
  health: (c) => c.health || ["health_problem", "emergency"].includes(c.intent),
};

export function render(ui, data) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const range = ui.callsRange === 30 ? 30 : 7;
  const from = addDays(clock, -range);
  const all = mine.flatMap((p) => callsOf(p).filter((c) => c.date >= from).map((c) => ({ ...c, p })));
  const filter = FILTERS.includes(ui.callsFilter) ? ui.callsFilter : "all";
  const counts = Object.fromEntries(FILTERS.map((f) => [f, all.filter(match[f]).length]));
  const list = all.filter(match[filter]).sort((a, b) => b.date.localeCompare(a.date) || (b.time || "99").localeCompare(a.time || "99"));
  const result = (c) => {
    if (c.relative) return `<span class="sn-tag">${L.relative}</span>`;
    if (!c.answered) return `<span class="sn-tag is-warn">${c.p.sex === "F" ? T.card.noAnswerF : T.card.noAnswer}</span>`;
    const warn = ["emergency", "health_problem", "low_mood"].includes(c.intent);
    return `<span class="sn-tag${warn ? " is-warn" : ""}">${esc(T.intent[c.intent] || c.intent || "")}</span>`;
  };
  const rows = list.slice(0, 400).map((c) => `<tr tabindex="0" data-action="open-card" data-id="${esc(c.p.id)}">
    <td>${fmtDate(c.date)}${c.time ? `<br><span class="sn-muted">${c.time}</span>` : ""}${c.live ? `<br><span class="sn-tag">${L.live}</span>` : ""}</td>
    <td><b>${esc(c.p.name)}</b><br><span class="sn-muted">${c.p.age}</span></td>
    <td>${result(c)}</td>
    <td>${c.answered ? moodBadge(c.mood) : ""}</td>
    <td>${esc((c.items || []).map(itemLabel).join(", "))}</td>
    <td class="sn-hide-s">${c.text ? `<q>${esc(c.text)}</q>` : ""}${c.note ? `<br><span class="sn-muted">${esc(c.note)}</span>` : ""}</td>
  </tr>`).join("");
  const rangeTabs = `<nav class="tabs" aria-label="Období">${[7, 30].map((r) => `<button type="button" data-action="calls-range" data-range="${r}" aria-pressed="${range === r}">${L.range[r]}</button>`).join("")}</nav>`;
  return `<header class="pagehead"><h1>${L.title}</h1><p>${L.sub(all.length, fmtDate(from))}</p></header>
    <div class="sn-toolbar">${tabs("calls-filter", FILTERS, L.filters, filter, counts)}${rangeTabs}</div>
    ${list.length ? `<div class="tablewrap"><table class="sn-calls">
      <thead><tr>${L.cols.map((c, i) => `<th${i === 5 ? ' class="sn-hide-s"' : ""}>${c}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody></table></div>` : `<p class="empty">${L.empty}</p>`}`;
}
