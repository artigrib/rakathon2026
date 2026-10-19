// Přehled: coverage (who we reached in 7 days), share "v pořádku", mood trend of 30 days, needs, all districts.
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { esc, fmtDate } from "core/util.js";
import { addDays, alertOf, callsOf, groups, ITEMS, itemLabel, lastAnswered, lostOf, openNeeds, stageOf } from "../domain.js";
import { section } from "../ui.js";

const O = T.overview;
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)} %` : O.none);
const dec = (x) => (x == null ? O.none : x.toFixed(1).replace(".", ","));
const avg = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);

function stats(records, clock, plans) {
  const active = records.filter((p) => !["paused", "declined"].includes(stageOf(p)));
  const from7 = addDays(clock, -7);
  const reached = active.filter((p) => callsOf(p).some((c) => c.answered && c.date >= from7));
  const last = active.map((p) => lastAnswered(p)).filter(Boolean);
  const moods7 = active.flatMap((p) => callsOf(p).filter((c) => c.answered && c.mood && c.date >= from7).map((c) => c.mood));
  return {
    n: records.length, active: active.length, reached: reached.length,
    ok: last.filter((c) => c.intent === "ok").length, answered: last.length,
    mood: avg(moods7), needs: records.reduce((s, p) => s + openNeeds(p).length, 0),
    alerts: records.filter((p) => alertOf(p) || lostOf(p, clock, plans)).length,
  };
}

function trend(records, clock) {
  const days = 30, W = 640, H = 180, L = 28, R = 8, Tp = 10, B = 24;
  const from = addDays(clock, -days);
  const byDay = new Map();
  for (const p of records) for (const c of callsOf(p)) if (c.answered && c.mood && c.date >= from && c.date <= clock) byDay.set(c.date, [...(byDay.get(c.date) || []), c.mood]);
  const pts = [...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([d, ms]) => ({ d, m: avg(ms), n: ms.length }));
  if (!pts.length) return `<p class="empty">${O.none}</p>`;
  const x = (d) => L + ((Date.parse(d) - Date.parse(from)) / (days * 864e5)) * (W - L - R);
  const y = (m) => Tp + (1 - (m - 1) / 4) * (H - Tp - B);
  const grid = [1, 2, 3, 4, 5].map((m) => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(m)}" y2="${y(m)}"/><text x="${L - 8}" y="${y(m) + 4}" text-anchor="end">${m}</text>`).join("");
  const ticks = [0, 10, 20, 30].map((i) => { const d = addDays(from, i); return `<text x="${x(d)}" y="${H - 6}" text-anchor="middle">${fmtDate(d).replace(/ \d{4}$/, "")}</text>`; }).join("");
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.m).toFixed(1)}`).join("");
  const desc = pts.map((p) => `${fmtDate(p.d)} ${dec(p.m)}`).join(", ");
  return `<svg class="sn-trend" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(O.trend)}: ${esc(desc)}">${grid}${ticks}
    <path class="ln" d="${path}"/></svg><p class="note">${O.trendNote}</p>`;
}

function bars(rows) {
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return `<ul class="stats">${rows.map(([k, v]) => `<li><div>${esc(k)}<div class="bar"><i style="width:${Math.max(0.5, (v / max) * 100)}%"></i></div></div><b>${v}</b></li>`).join("")}</ul>`;
}

export function render(ui, data) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const plans = data.live?.plans;
  const s = stats(mine, clock, plans);
  const tiles = [[O.stats[0], s.active], [O.stats[1], `${s.reached} (${pct(s.reached, s.active)})`], [O.stats[2], pct(s.ok, s.answered)],
    [O.stats[3], dec(s.mood)], [O.stats[4], s.needs], [O.stats[5], s.alerts]];
  const coverage = `<ul class="stats">${tiles.map(([k, v], i) => `<li class="${i === 5 && s.alerts ? "is-lost" : ""}"><div>${k}</div><b>${v}</b></li>`).join("")}</ul>`;

  const from30 = addDays(clock, -30);
  const items = Object.keys(ITEMS).map((k) => [itemLabel(k), mine.reduce((n, p) => n + callsOf(p).filter((c) => c.date >= from30 && c.items?.includes(k)).length, 0)])
    .filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
  const lastMoods = [5, 4, 3, 2, 1].map((m) => [`${m}: ${T.mood[m]}`, mine.filter((p) => lastAnswered(p)?.mood === m).length]);

  const rows = groups(data.patients).map((g) => {
    const recs = data.patients.filter((p) => p.district === g);
    const t = stats(recs, clock, plans);
    return `<tr tabindex="0" data-action="pick-district" data-gp="${esc(g)}"><td>${esc(g)}</td><td class="n">${t.n}</td><td class="n">${pct(t.reached, t.active)}</td>
      <td class="n">${pct(t.ok, t.answered)}</td><td class="n">${dec(t.mood)}</td><td class="n">${t.needs}</td><td class="n"><b>${t.alerts}</b></td></tr>`;
  }).join("");
  const table = `<div class="tablewrap"><table><thead><tr>${O.cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;

  return `<header class="pagehead"><h1>${O.title}</h1><p>${O.sub(mine.length, fmtDate(clock))}</p></header>
    ${section("coverage", "", O.coverage, coverage)}
    ${section("trend", "", O.trend, trend(mine, clock))}
    ${section("needs", "", O.needs, items.length ? bars(items) : `<p class="empty">${O.none}</p>`)}
    ${section("moods", "", O.moods, bars(lastMoods))}
    ${section("districts", "", O.districts, table)}`;
}
