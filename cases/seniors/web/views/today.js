// Start screen of the operator: what needs a person now, who to call today, who does not answer, who is fine.
// Needs live in the basket (one link line); a senior who asked to be called back is a call to make today.
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { row } from "core/components/row.js";
import { esc, fmtDate } from "core/util.js";
import { alertOf, batchOf, bySurname, callsOf, dueToday, lostOf, openNeeds, stageDate, stageOf } from "../domain.js";
import { section } from "../ui.js";

const ALERT_ORDER = { crisis: 0, emergency: 0, health: 1, visit: 2, escalate: 3, lowMood: 4 };

export function render(ui, data, rowCtx) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const plans = data.live?.plans;
  const seen = new Set();
  const take = (list) => list.filter((p) => !seen.has(p.id) && seen.add(p.id));
  const rows = (list, extra = () => ({})) => list.map((p) => row(p, { ...rowCtx.of(p), ...extra(p) })).join("");

  const lost = new Map(mine.map((p) => [p.id, lostOf(p, clock, plans)]).filter(([, l]) => l));
  const alerts = take(mine.filter((p) => alertOf(p) || lost.has(p.id))
    .sort((a, b) => (ALERT_ORDER[alertOf(a)] ?? 9) - (ALERT_ORDER[alertOf(b)] ?? 9) || stageDate(a).localeCompare(stageDate(b))));
  const noAnswer = take(mine.filter((p) => stageOf(p) === "no_answer"));
  // today's calls: the scheduled check-ins and whoever asked to be called back (the operator calls by hand, first in the list)
  const callback = (p) => stageOf(p) === "callback";
  const from = (p) => (p.schedule?.from || "").padStart(5, "0"); // "8:30" before "13:00"
  const due = take(mine.filter((p) => dueToday(p) || callback(p))
    .sort((a, b) => callback(b) - callback(a) || from(a).localeCompare(from(b)) || bySurname(a, b)));
  const okToday = mine.filter((p) => stageOf(p) === "ok" && callsOf(p)[0]?.date === clock && !seen.has(p.id));
  const batch = batchOf(mine);
  const needs = mine.reduce((n, p) => n + openNeeds(p).length, 0);
  const S = T.sections;

  const elsewhere = batch.filter((p) => !due.includes(p)).length; // today's calls listed in the sections above
  const batchBlock = batch.length ? `<div class="batch"><button type="button" class="btn btn--primary btn--big" data-action="approve-batch">${T.today.batch(batch.length)}</button>
    <p class="sn-muted">${T.today.batchHint}${elsewhere ? ` ${S.due.elsewhere(elsewhere)}` : ""}</p></div>` : "";
  const empty = (k) => `<p class="empty">${S[k].empty}</p>`;
  const okList = okToday.length ? `<details class="sn-done"><summary>${S.ok.show} (${okToday.length})</summary>${rows(okToday)}</details>` : empty("ok");

  return `<header class="pagehead"><h1>${T.today.title(fmtDate(clock))}</h1>
      <p class="summary">${T.today.summary(alerts.length, due.length)}</p>
      <p><button type="button" class="btn btn--link" data-action="pick-view" data-view="basket">${esc(T.today.basket(needs))}</button></p>
      ${!due.length && !alerts.length ? `<p>${T.today.allDone}</p>` : ""}</header>
    ${section("alerts", alerts.length, S.alerts.title, alerts.length ? rows(alerts, (p) => ({ lost: lost.get(p.id) })) : empty("alerts"), { due: true, hint: S.alerts.hint, cls: alerts.length ? " section--lost" : "" })}
    ${section("due", due.length, S.due.title, batchBlock + (due.length ? rows(due) : batch.length ? "" : empty("due")), { due: true, hint: S.due.hint })}
    ${section("noanswer", noAnswer.length, S.noAnswer.title, noAnswer.length ? rows(noAnswer) : empty("noAnswer"), { hint: S.noAnswer.hint })}
    ${section("ok", okToday.length, S.ok.title, okList, { cls: " section--quiet" })}`;
}

/** Navigation count: what needs a person now (alerts and seniors getting lost). */
export const badge = (mine, clock, plans) => mine.filter((p) => alertOf(p) || lostOf(p, clock, plans)).length;
