// Přehled for the manager: the districts first, then this week's numbers of the chosen district, the mood trend of
// 30 days, what seniors need, the mood at the last call.
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { esc, fmtDate } from "core/util.js";
import { store } from "core/state.js";
import { addDays, alertOf, callsOf, daysBetween, groups, ITEMS, itemLabel, lastAnswered, latestMood, lostOf, needsOf, openNeeds, stageOf } from "../domain.js";
import { section } from "../ui.js";

const O = T.overview;
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)} %` : O.none);
const dec = (x) => (x == null ? O.none : x.toFixed(1).replace(".", ","));
const avg = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);

function stats(records, clock, plans) {
  const active = records.filter((p) => !["paused", "declined"].includes(stageOf(p)));
  const from7 = addDays(clock, -7);
  const reached = active.filter((p) => callsOf(p).some((c) => c.answered && c.date >= from7));
  const moods7 = active.flatMap((p) => callsOf(p).filter((c) => c.answered && c.mood && c.date >= from7).map((c) => c.mood));
  // without an answer for more than two days: the stage says no answer and the last call heard is older than 2 days
  const noAnswer = active.filter((p) => stageOf(p) === "no_answer" && daysBetween(lastAnswered(p)?.date || p.since, clock) > 2);
  const lowMood = active.filter((p) => stageOf(p) === "low_mood" || (latestMood(p) || 5) <= 2);
  const open = records.flatMap((p) => openNeeds(p));
  const oldest = open.length ? Math.max(...open.map((n) => daysBetween(n.date, clock))) : 0;
  // closed in 7 days: needs marked done that came up in the last 7 days + "resolve" decisions recorded in this demo
  const doneNeeds = records.flatMap((p) => needsOf(p)).filter((n) => n.status === "done" && n.date >= from7).length;
  const resolved = records.reduce((s, p) => s + (store.get(p.id).journey || []).filter((e) => e.event === "resolve" && !e.ignored && e.date >= from7).length, 0);
  return {
    n: records.length, active: active.length, reached: reached.length, noAnswer: noAnswer.length, lowMood: lowMood.length,
    mood: avg(moods7), needs: open.length, oldest, done: doneNeeds + resolved,
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
  const ticks = [0, 10, 20, 30].map((i) => { const d = addDays(from, i); return `<text x="${x(d)}" y="${H - 6}" text-anchor="middle">${fmtDate(d).replace(/ \d{4}$/, "")}</text>`; }).join("");
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
  const tiles = [
    ["reached", `${s.reached}`, pct(s.reached, s.active), false],
    ["noAnswer", `${s.noAnswer}`, "", s.noAnswer > 0],
    ["lowMood", `${s.lowMood}`, "", s.lowMood > 0],
    ["needs", `${s.needs}`, s.needs ? O.oldest(s.oldest) : "", false],
    ["done", `${s.done}`, "", false],
  ];
  const week = `<ul class="stats">${tiles.map(([k, v, sub, warn]) => `<li class="${warn ? "is-lost" : ""}"><div>${O.stats[k]}${sub ? `<small>${sub}</small>` : ""}</div><b>${v}</b></li>`).join("")}</ul>`;

  const from30 = addDays(clock, -30);
  const items = Object.keys(ITEMS).map((k) => [itemLabel(k), mine.reduce((n, p) => n + callsOf(p).filter((c) => c.date >= from30 && c.items?.includes(k)).length, 0)])
    .filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
  const lastMoods = [5, 4, 3, 2, 1].map((m) => [`${m}: ${T.mood[m]}`, mine.filter((p) => lastAnswered(p)?.mood === m).length]);

  const rows = groups(data.patients).map((g) => {
    const recs = data.patients.filter((p) => p.district === g);
    const t = stats(recs, clock, plans);
    return `<tr tabindex="0" data-action="pick-district" data-gp="${esc(g)}"${g === ui.gp ? ' aria-current="true"' : ""}><td>${g === ui.gp ? `<b>${esc(g)}</b>` : esc(g)}</td><td class="n">${t.n}</td><td class="n">${pct(t.reached, t.active)}</td>
      <td class="n">${t.noAnswer}</td><td class="n">${t.lowMood}</td><td class="n">${t.needs}</td><td class="n"><b>${t.alerts}</b></td></tr>`;
  }).join("");
  const table = `<div class="tablewrap"><table><thead><tr>${O.cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;

  return `<header class="pagehead"><h1>${O.title}</h1><p>${O.sub(mine.length, fmtDate(clock))}</p></header>
    ${section("districts", "", O.districts, table)}
    ${section("coverage", "", `${O.coverage}: ${esc(ui.gp || "")}`, week)}
    ${section("trend", "", O.trend, trend(mine, clock))}
    ${section("needs", "", O.needs, items.length ? bars(items) : `<p class="empty">${O.none}</p>`)}
    ${section("moods", "", O.moods, bars(lastMoods))}`;
}
