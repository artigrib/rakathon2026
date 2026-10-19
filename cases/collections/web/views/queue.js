// Fronta: the work queue grouped by strategy. Automated strategies wait for one approval of the first message;
// people (operator, supervisor) get what the automation must not or cannot do. The rest is watched by the system.
import { QUEUE } from "../config.js";
import { T } from "../i18n.js";
import { mineOf } from "core/case.js";
import { fmtDate } from "core/util.js";
import { row } from "core/components/row.js";
import { store } from "core/state.js";
import { batchOf, isContactDay, lostOf, ownerOf, queueOf, stageOf } from "../domain.js";

const Q = T.queue;
const STYLE = `<style>
  .qhint { margin: 0 0 12px; color: var(--ink-2); }
  .window { border-left: 4px solid var(--accent); padding: 4px 0 4px 14px; margin: 0 0 8px; color: var(--ink-2); }
  .window.is-closed { border-color: var(--warn); color: var(--ink); }
  .row .muted { color: var(--ink-2); font-size: var(--t-s); align-self: center; }
</style>`;

const urgency = (p) => ({ human_handoff: 0, wrong_contact: 1, refi_accepted: 2 }[stageOf(p)] ?? 3);

export function render(ui, data, rowCtx) {
  const mine = mineOf(data, ui);
  const clock = data.live?.clock || data.refDate;
  const plans = data.live?.plans;
  const lost = new Map(mine.map((p) => [p.id, lostOf(p, clock, plans)]).filter(([, l]) => l));
  const by = Object.fromEntries(QUEUE.map((s) => [s, []]));
  for (const p of mine) { const q = queueOf(p); if (q && !lost.has(p.id)) by[q].push(p); }
  const open = isContactDay(clock);
  const batch = batchOf(mine);

  const own = {};
  for (const p of mine) { const o = ownerOf(p, clock, plans); own[o] = (own[o] || 0) + 1; }
  const summary = `<p class="summary">${Q.summary(mine.length, own.operator || 0, own.supervisor || 0, own.system || 0, own.done || 0, own.lost || 0)}</p>`;
  const window = `<p class="window${open ? "" : " is-closed"}">${open ? Q.window : Q.closed(fmtDate(clock))}</p>`;
  const batchBlock = batch.length ? `<div class="batch"><button type="button" class="btn btn--primary btn--big" data-action="approve-batch">${Q.batch(batch.length)}</button><p>${Q.batchHint}</p></div>` : "";

  const lostRows = mine.filter((p) => lost.has(p.id)).sort((a, b) => lost.get(b.id).days - lost.get(a.id).days);
  const lostBlock = lostRows.length ? `<section class="section grid section--lost" aria-labelledby="h-lost">
      <div class="section__aside"><span class="count is-due">${lostRows.length}</span><h2 id="h-lost">${Q.sections.lost.title}</h2></div>
      <div class="section__body">${lostRows.map((p) => row(p, { ...rowCtx.of(p), lost: lost.get(p.id) })).join("")}</div>
    </section>` : "";

  const sections = QUEUE.map((s) => {
    const rows = by[s].sort((a, b) => urgency(a) - urgency(b) || (b.dpd || 0) - (a.dpd || 0));
    const due = rows.filter((p) => !store.get(p.id).skipped).length;
    const S = Q.sections[s];
    return `<section class="section grid" aria-labelledby="h-${s}">
      <div class="section__aside"><span class="count${due ? " is-due" : ""}">${due}</span><h2 id="h-${s}">${S.title}</h2>
        <p>${T.strategy[s] || ""}</p></div>
      <div class="section__body"><p class="qhint">${S.hint}</p>
        ${rows.length ? rows.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${S.empty}</p>`}
      </div>
    </section>`;
  }).join("");

  const waiting = mine.filter((p) => ownerOf(p, clock, plans) === "system" && stageOf(p))
    .sort((a, b) => (store.get(b.id).journey?.at(-1)?.date || "").localeCompare(store.get(a.id).journey?.at(-1)?.date || ""));
  const W = Q.sections.waiting;
  const waitingBlock = `<section class="section grid section--quiet" aria-labelledby="h-waiting">
      <div class="section__aside"><span class="count">${waiting.length}</span><h2 id="h-waiting">${W.title}</h2></div>
      <div class="section__body"><p class="qhint">${W.hint}</p>${waiting.length ? waiting.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${W.empty}</p>`}</div>
    </section>`;

  return `${STYLE}<header class="pagehead"><h1>${Q.title}</h1>${summary}${window}${batchBlock}</header>${lostBlock}${sections}${waitingBlock}`;
}

/** Things waiting for a person (navigation badge). */
export const badge = (mine, clock, plans) => mine.filter((p) => ["operator", "supervisor", "lost"].includes(ownerOf(p, clock, plans)) && !store.get(p.id).skipped).length;
