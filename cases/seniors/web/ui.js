// Small shared pieces of the Jsem v pořádku screens: mood words and chart, need chips, section frame, the case's styles.
// Everything case-specific in CSS lives here under html.case-seniors, so the shared stylesheets stay as they are for screening.
import { T } from "./i18n.js";
import { esc, fmtDate } from "core/util.js";
import { addDays, clock, itemLabel } from "./domain.js";

const CSS = `
.sn-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-top: 16px; }
.sn-tile { border-top: 2px solid var(--ink); padding: 12px 0 8px; display: grid; gap: 6px; align-content: start; min-width: 0; }
.sn-tile .muted, .sn-muted { color: var(--ink-2); font-size: var(--t-s); }
.sn-tile.is-alert { border-top-color: var(--warn); }
.sn-tile.is-alert b.sn-state { color: var(--warn); }
.sn-tile .sn-mood { font-size: var(--t-s); }
.sn-chart { display: block; width: 100%; max-width: 420px; height: auto; color: var(--ink-2); }
.sn-chart .ln { fill: none; stroke: var(--accent); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.sn-chart .grid { stroke: var(--hair); stroke-width: 1; }
.sn-chart .ax { stroke: var(--ink-2); stroke-width: 1; }
.sn-chart text { fill: var(--ink-2); font-size: 11px; font-family: var(--font); }
.sn-chart .pt { fill: var(--paper); stroke: var(--accent); stroke-width: 2; }
.sn-chart .pt.low { stroke: var(--warn); }
.sn-chart .pt.last { fill: var(--accent); }
.sn-chips { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; margin: 0; padding: 0; }
.sn-chip { font-size: var(--t-s); border: 1px solid var(--ink-2); padding: 2px 8px; white-space: nowrap; }
.sn-chip.is-new { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.sn-chip.is-done { opacity: .55; text-decoration: line-through; }
.sn-mood { display: inline-block; font-weight: 600; white-space: nowrap; }
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
.sn-rel { display: flex; flex-wrap: wrap; gap: 8px 20px; align-items: center; justify-content: space-between; }
.sn-rel .kv { flex: 1 1 14rem; }
.sn-note { display: grid; grid-template-columns: 11rem minmax(0, 1fr); gap: 4px 12px; margin: 0; }
.sn-note dt { color: var(--ink-2); } .sn-note dd { margin: 0; }
.sn-sim { margin-top: 4px; padding: 12px 14px; background: var(--field); border: 1px dashed var(--ink-2); }
.sn-sim summary { cursor: pointer; font-weight: 600; min-height: 36px; display: flex; align-items: center; gap: 8px; }
.sn-sim p { margin: 6px 0 10px; color: var(--ink-2); font-size: var(--t-s); }
/* overview tiles: the number never wraps */
.case-seniors .stats li { grid-template-columns: minmax(0, 1fr) auto; }
.case-seniors .stats b { white-space: nowrap; }
.case-seniors .stats small { display: block; color: var(--ink-2); font-size: var(--t-s); font-weight: 400; }
@media (max-width: 860px) {
  .sn-hist li { grid-template-columns: 1fr; }
  .sn-calls .sn-hide-s { display: none; }
  .sn-note, .case-seniors .kv--wide { grid-template-columns: 8.5rem minmax(0, 1fr); }
  /* the presenter panel goes up into the free right part of the header row, off the row buttons */
  .case-seniors .demo { top: 8px; bottom: auto; }
  .case-seniors .demo[open] { max-height: calc(100dvh - 16px); }
  .case-seniors .toast { bottom: calc(16px + env(safe-area-inset-bottom, 0px)); }
}
@media (max-width: 600px) {
  .sn-basket .sn-need { grid-template-columns: 1fr; }
  .sn-basket .sn-need .actions { justify-content: flex-start; }
  .case-seniors .nav { gap: 14px; font-size: var(--t-s); padding-right: 16px; }
}
`;
if (typeof document !== "undefined" && !document.getElementById("seniors-css")) {
  const s = document.createElement("style");
  s.id = "seniors-css";
  s.textContent = CSS;
  document.head.appendChild(s);
  document.documentElement.classList.add("case-seniors");
  if (!document.querySelector('link[rel~="icon"]')) { // tab icon: a teal circle with a check (the app's accent)
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#11615d"/><path d="M9 16.5l5 5 9-10" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    const l = document.createElement("link");
    l.rel = "icon"; l.type = "image/svg+xml"; l.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
    document.head.appendChild(l);
  }
}

/** Section frame of the core styles: count + title on the left, the work on the right. */
export const section = (id, count, title, body, { due = false, hint = "", cls = "" } = {}) => `<section class="section grid${cls}" aria-labelledby="h-${id}">
  <div class="section__aside">${count === "" ? "" : `<span class="count${due && count ? " is-due" : ""}">${count}</span>`}<h2 id="h-${id}">${title}</h2>${hint ? `<p>${hint}</p>` : ""}</div>
  <div class="section__body">${body}</div></section>`;

/** Mood as a word with the number: "smutná (2)". */
export const moodBadge = (m) => (m ? `<span class="sn-mood${m <= 2 ? " is-low" : ""}">${esc(T.moodWord(m))}</span>` : `<span class="sn-mood sn-muted">·</span>`);

/** Mood of the last `days` days as a line with an axis (y = mood 1…5, x = day). points: [{date, mood}] oldest first. */
export function moodChart(points, days = 30) {
  if (!points.length) return `<p class="sn-muted">${T.card.moodNone}</p>`;
  const W = 420, H = 150, L = 30, R = 10, Tp = 8, B = 22;
  const from = addDays(clock(), -days);
  const x = (d) => L + ((Date.parse(d) - Date.parse(from)) / (days * 864e5)) * (W - L - R);
  const y = (m) => Tp + (1 - (m - 1) / 4) * (H - Tp - B);
  const grid = [1, 2, 3, 4, 5].map((m) => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(m)}" y2="${y(m)}"/><text x="${L - 8}" y="${y(m) + 4}" text-anchor="end">${m}</text>`).join("");
  const ticks = [0, 15, 30].map((i) => { const d = addDays(from, i); return `<text x="${x(d)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === 30 ? "end" : "middle"}">${fmtDate(d).replace(/ \d{4}$/, "")}</text>`; }).join("");
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.mood).toFixed(1)}`).join("");
  const label = points.map((p) => `${fmtDate(p.date)}: ${T.moodWord(p.mood)}`).join(", ");
  return `<svg class="sn-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T.card.moodChart)}: ${esc(label)}">
    ${grid}<line class="ax" x1="${L}" x2="${W - R}" y1="${y(1)}" y2="${y(1)}"/>${ticks}
    <path class="ln" d="${path}"/>
    ${points.map((p, i) => `<circle class="pt${p.mood <= 2 ? " low" : ""}${i === points.length - 1 ? " last" : ""}" cx="${x(p.date).toFixed(1)}" cy="${y(p.mood).toFixed(1)}" r="4"/>`).join("")}
  </svg>`;
}

/** Need chips: [{item, status}] or item keys. */
export const chips = (needs) => (needs.length ? `<ul class="sn-chips">${needs.map((n) => typeof n === "string"
  ? `<li class="sn-chip">${esc(itemLabel(n))}</li>`
  : `<li class="sn-chip is-${n.status}" title="${esc(T.basket.status[n.status])}">${esc(itemLabel(n.item))}</li>`).join("")}</ul>` : "");

/** Filter tabs of the core style. */
export const tabs = (action, keys, labels, current, counts = {}) => `<nav class="tabs">${keys.map((k) => `<button type="button" data-action="${action}" data-filter="${k}" aria-pressed="${current === k}">
  ${labels[k]}${counts[k] != null ? ` <span class="muted">${counts[k]}</span>` : ""}</button>`).join("")}</nav>`;
