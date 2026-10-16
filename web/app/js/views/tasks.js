// Default screen: what the practice has to do this week, most urgent first.
import { SECTIONS } from "../config.js";
import { T } from "../i18n/cs.js";
import { batchOf, lostOf, phaseOf, stageOf, taskOf } from "../domain.js";
import { sectionOf } from "../fsm.js";
import { row } from "../components/row.js";
import { store } from "../state.js";

const ORDER = { nurse_call: 0, callback: 1, interested: 2, ldct: 0, booked: 1 };

function batchBlock(mine) {
  const n = batchOf(mine).length;
  return n ? `<div class="batch"><button type="button" class="btn btn--primary btn--big" data-action="approve-batch">${T.batch.approve(n)}</button><p>${T.batch.hint}</p></div>` : "";
}

export function tasks(ui, data, rowCtx) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const clock = data.live?.clock || data.refDate;
  const lost = new Map(mine.map((p) => [p.id, lostOf(p, clock, data.live?.plans)]).filter(([, l]) => l));
  const by = Object.fromEntries(SECTIONS.map((s) => [s, []]));
  for (const p of mine) { const t = taskOf(p); if (t && !lost.has(p.id)) by[t].push(p); }
  const total = SECTIONS.reduce((n, s) => n + (s === "invite" ? batchOf(by.invite).length : by[s].length), 0);

  // Getting lost: first, before anything else. Each row says why in words.
  const lostRows = mine.filter((p) => lost.has(p.id)).sort((a, b) => lost.get(b.id).days - lost.get(a.id).days);
  const lostBlock = lostRows.length ? `<section class="section grid section--lost" aria-labelledby="h-lost">
      <div class="section__aside"><span class="count is-due">${lostRows.length}</span><h2 id="h-lost">${T.sections.lost.title}</h2></div>
      <div class="section__body">${lostRows.map((p) => row(p, { ...rowCtx.of(p), lost: lost.get(p.id) })).join("")}</div>
    </section>` : "";

  // One line that answers "is anybody lost?": everyone in the programme has an owner and a next step.
  const inProgramme = mine.filter((p) => stageOf(p) || taskOf(p));
  const sys = mine.filter((p) => stageOf(p) && sectionOf(stageOf(p)) === "waiting" && !lost.has(p.id)).length;
  const done = mine.filter((p) => stageOf(p) && phaseOf(p) === "done").length;
  const yours = inProgramme.length - sys - done - lost.size;
  const summary = `<p class="summary">${T.summary(inProgramme.length, yours, sys, done, lost.size)}</p>`;

  const sections = SECTIONS.map((s) => {
    const rows = by[s].sort((a, b) => (ORDER[stageOf(a)] ?? 9) - (ORDER[stageOf(b)] ?? 9));
    const due = s === "invite" ? batchOf(rows).length : rows.length;
    const S = T.sections[s];
    return `<section class="section grid" aria-labelledby="h-${s}">
      <div class="section__aside">
        <span class="count${due ? " is-due" : ""}">${due}</span>
        <h2 id="h-${s}">${S.title}</h2>
      </div>
      <div class="section__body">
        ${s === "invite" ? batchBlock(rows) : ""}
        ${rows.length ? rows.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${S.empty}</p>`}
      </div>
    </section>`;
  }).join("");

  // Invited, no reply yet: nothing to do, the contact plan runs by itself. Shown so the nurse sees where they went.
  const waiting = mine.filter((p) => stageOf(p) && sectionOf(stageOf(p)) === "waiting" && !lost.has(p.id))
    .sort((a, b) => (store.get(b.id).journey?.at(-1)?.date || "").localeCompare(store.get(a.id).journey?.at(-1)?.date || ""));
  const W = T.sections.waiting;
  const waitingBlock = `<section class="section grid section--quiet" aria-labelledby="h-waiting">
      <div class="section__aside"><span class="count">${waiting.length}</span><h2 id="h-waiting">${W.title}</h2></div>
      <div class="section__body">${waiting.length ? waiting.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${W.empty}</p>`}</div>
    </section>`;

  return `<header class="pagehead">
      <h1>${T.tasks.title}</h1>${summary}${total || lost.size ? "" : `<p>${T.tasks.allDone}</p>`}
    </header>${lostBlock}${sections}${waitingBlock}`;
}

/** Number of things waiting for the practice (shown in the navigation). */
export const taskCount = (mine, clock, plans) => mine.filter((p) => (taskOf(p) && taskOf(p) !== "invite") || (!taskOf(p) && lostOf(p, clock, plans))).length + batchOf(mine).length;
