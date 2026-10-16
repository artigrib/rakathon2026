// Default screen: what the practice has to do this week, most urgent first.
import { SECTIONS } from "../config.js";
import { T } from "../i18n/cs.js";
import { fmtDate, countBy } from "../util.js";
import { batchOf, plannedContact, stageOf, taskOf } from "../domain.js";
import { row } from "../components/row.js";

const ORDER = { nurse_call: 0, callback: 1, interested: 2, ldct: 0, booked: 1 };

function batchBlock(mine) {
  const batch = batchOf(mine);
  if (!batch.length) return "";
  const mix = Object.entries(countBy(batch, (p) => plannedContact(p).channel))
    .map(([ch, n]) => T.batch.mix(n, T.channel[ch])).join(", ");
  return `<div class="batch"><p>${T.batch.text(mix)}</p>
    <button type="button" class="btn btn--primary btn--big" data-action="approve-batch">${T.batch.approve(batch.length)}</button></div>`;
}

export function tasks(ui, data, rowCtx) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const by = Object.fromEntries(SECTIONS.map((s) => [s, []]));
  for (const p of mine) { const t = taskOf(p); if (t) by[t].push(p); }
  const total = SECTIONS.reduce((n, s) => n + (s === "invite" ? batchOf(by.invite).length : by[s].length), 0);

  const sections = SECTIONS.map((s) => {
    const rows = by[s].sort((a, b) => (ORDER[stageOf(a)] ?? 9) - (ORDER[stageOf(b)] ?? 9));
    const due = s === "invite" ? batchOf(rows).length : rows.length;
    const S = T.sections[s];
    return `<section class="section grid" aria-labelledby="h-${s}">
      <div class="section__aside">
        <span class="count${due ? " is-due" : ""}">${due}</span>
        <h2 id="h-${s}">${S.title}</h2>
        <p>${S.what}</p>
      </div>
      <div class="section__body">
        ${s === "invite" ? batchBlock(rows) : ""}
        ${rows.length ? rows.map((p) => row(p, rowCtx.of(p))).join("") : `<p class="empty">${S.empty}</p>`}
      </div>
    </section>`;
  }).join("");

  return `<header class="pagehead">
      <h1>${T.tasks.title}</h1>
      <p>${T.tasks.sub(mine.length, fmtDate(data.refDate))}${total ? "" : ` ${T.tasks.allDone}`}</p>
    </header>${sections}`;
}

/** Number of things waiting for the practice (shown in the navigation). */
export const taskCount = (mine) => mine.filter((p) => taskOf(p) && taskOf(p) !== "invite").length + batchOf(mine).length;
