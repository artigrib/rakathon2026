// Small shared pieces of the Jsem v pořádku screens: mood sparkline, need chips, section frame, the case's styles.
import { T } from "./i18n.js";
import { esc, fmtDate } from "core/util.js";
import { addDays, clock, itemLabel } from "./domain.js";

const CSS = `
.sn-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-top: 16px; }
.sn-tile { border-top: 2px solid var(--ink); padding: 12px 0 8px; display: grid; gap: 6px; align-content: start; min-width: 0; }
.sn-tile .muted, .sn-muted { color: var(--ink-2); font-size: var(--t-s); }
.sn-tile.is-alert { border-top-color: var(--warn); }
.sn-tile.is-alert b.sn-state { color: var(--warn); }
.sn-spark { display: block; width: 100%; max-width: 280px; height: 44px; color: var(--ink-2); }
.sn-spark .ln { fill: none; stroke: var(--ink); stroke-width: 1.5; }
.sn-spark .grid { stroke: var(--hair); stroke-width: 1; }
.sn-spark .pt { fill: var(--ink); }
.sn-spark .pt.low { fill: var(--warn); }
.sn-spark .pt.last { fill: var(--accent); }
.sn-chips { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; margin: 0; padding: 0; }
.sn-chip { font-size: var(--t-s); border: 1px solid var(--ink-2); padding: 2px 8px; white-space: nowrap; }
.sn-chip.is-new { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.sn-chip.is-done { opacity: .55; text-decoration: line-through; }
.sn-mood { display: inline-block; min-width: 2.2em; font-weight: 700; }
.sn-mood.is-low { color: var(--warn); }
.sn-calls td, .sn-calls th { vertical-align: top; }
.sn-calls q { font-style: italic; color: var(--ink); }
.sn-calls tr[data-action] { cursor: pointer; }
.sn-calls tr[data-action]:hover td { background: var(--field); }
.sn-tag { font-size: var(--t-s); color: var(--ink-2); }
.sn-tag.is-warn { color: var(--warn); font-weight: 600; }
.sn-basket .sn-need { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 16px; padding: 12px 0; border-bottom: 1px solid var(--hair); align-items: center; }
.sn-basket .who { font-weight: 700; }
.sn-status { font-size: var(--t-s); font-weight: 600; }
.sn-status.is-new { color: var(--accent); }
.sn-status.is-done { color: var(--ink-2); }
.sn-toolbar { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; justify-content: space-between; }
.sn-trend { width: 100%; height: 180px; display: block; color: var(--ink-2); }
.sn-trend .ln { fill: none; stroke: var(--accent); stroke-width: 2.5; }
.sn-trend .grid { stroke: var(--hair); stroke-width: 1; }
.sn-trend text { fill: var(--ink-2); font-size: 11px; font-family: var(--font); }
.sn-hist { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.sn-hist li { display: grid; grid-template-columns: 7.5em minmax(0, 1fr); gap: 2px 10px; }
.sn-hist time { color: var(--ink-2); font-size: var(--t-s); }
.sn-hist q { display: block; font-style: italic; }
.sn-done { margin-top: 8px; }
.sn-done summary { cursor: pointer; min-height: var(--target); display: flex; align-items: center; color: var(--ink-2); text-decoration: underline; text-underline-offset: 4px; }
@media (max-width: 860px) { .sn-hist li { grid-template-columns: 1fr; } .sn-calls .sn-hide-s { display: none; } }
`;
if (typeof document !== "undefined" && !document.getElementById("seniors-css")) {
  const s = document.createElement("style");
  s.id = "seniors-css";
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Section frame of the core styles: count + title on the left, the work on the right. */
export const section = (id, count, title, body, { due = false, hint = "", cls = "" } = {}) => `<section class="section grid${cls}" aria-labelledby="h-${id}">
  <div class="section__aside">${count === "" ? "" : `<span class="count${due && count ? " is-due" : ""}">${count}</span>`}<h2 id="h-${id}">${title}</h2>${hint ? `<p>${hint}</p>` : ""}</div>
  <div class="section__body">${body}</div></section>`;

export const moodBadge = (m) => (m ? `<span class="sn-mood${m <= 2 ? " is-low" : ""}" title="${esc(T.mood[m])}">${m}/5</span>` : `<span class="sn-mood sn-muted">·</span>`);

/** Mood of the last 30 days as a sparkline (x = day, y = mood 1…5). points: [{date, mood}] oldest first. */
export function sparkline(points, days = 30) {
  if (!points.length) return `<p class="sn-muted">${T.card.moodNone}</p>`;
  const W = 280, H = 44, pad = 4;
  const from = addDays(clock(), -days);
  const x = (d) => pad + ((Date.parse(d) - Date.parse(from)) / (days * 864e5)) * (W - 2 * pad);
  const y = (m) => H - pad - ((m - 1) / 4) * (H - 2 * pad);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.mood).toFixed(1)}`).join("");
  const label = points.map((p) => `${fmtDate(p.date)}: ${p.mood}`).join(", ");
  return `<svg class="sn-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(T.card.mood)}: ${esc(label)}">
    <line class="grid" x1="0" x2="${W}" y1="${y(3)}" y2="${y(3)}"/>
    <path class="ln" d="${path}" vector-effect="non-scaling-stroke"/>
    ${points.map((p, i) => `<circle class="pt${p.mood <= 2 ? " low" : ""}${i === points.length - 1 ? " last" : ""}" cx="${x(p.date).toFixed(1)}" cy="${y(p.mood).toFixed(1)}" r="${i === points.length - 1 ? 3.2 : 2.2}"/>`).join("")}
  </svg>`;
}

/** Need chips: [{item, status}] or item keys. */
export const chips = (needs) => (needs.length ? `<ul class="sn-chips">${needs.map((n) => typeof n === "string"
  ? `<li class="sn-chip">${esc(itemLabel(n))}</li>`
  : `<li class="sn-chip is-${n.status}" title="${esc(T.basket.status[n.status])}">${esc(itemLabel(n.item))}</li>`).join("")}</ul>` : "");

/** Filter tabs of the core style. */
export const tabs = (action, keys, labels, current, counts = {}) => `<nav class="tabs">${keys.map((k) => `<button type="button" data-action="${action}" data-filter="${k}" aria-pressed="${current === k}">
  ${labels[k]}${counts[k] != null ? ` <span class="muted">${counts[k]}</span>` : ""}</button>`).join("")}</nav>`;
