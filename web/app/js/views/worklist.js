import { BUCKETS, CRITERIA } from "../config.js";
import { T } from "../i18n/cs.js";
import { fmtDate, html, countBy } from "../util.js";
import { batchOf, bucketOf, plannedContact } from "../domain.js";
import { shape } from "../components/shape.js";
import { patientRow } from "../components/patientRow.js";

export function worklist(ui, data) {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const counts = countBy(mine, bucketOf);
  const rows = mine.filter((p) => bucketOf(p) === ui.bucket);

  const tiles = BUCKETS.map((b) => html`<button type="button" class="tile" data-action="pick-bucket" data-bucket="${b.key}" aria-pressed="${ui.bucket === b.key}">
      ${shape(b.shape, true)}
      <span><span class="tile__count">${counts[b.key] || 0}</span> <span class="tile__label">${T.buckets[b.key].label}</span></span>
      <span class="tile__hint">${T.buckets[b.key].hint}</span>
    </button>`);

  const batch = batchOf(mine);
  const mix = Object.entries(countBy(batch, (p) => plannedContact(p).channel))
    .map(([ch, n]) => `<li>${T.channel[ch]} <b>${n}</b></li>`).join("");
  const toolbar = ui.bucket !== "contact" ? ""
    : batch.length
      ? html`<section class="batch" aria-labelledby="batch-h">
          <div><h2 id="batch-h">${T.batch.title(batch.length)}</h2><ul class="batch__mix">${mix}</ul><p>${T.batch.hint}</p></div>
          <button type="button" class="btn btn--primary btn--big" data-action="approve-batch">${T.batch.approve(batch.length)}</button>
        </section>`
      : `<p class="batch batch--done">${T.batch.done}</p>`;

  return html`
    <section class="pagehead">
      <h1>${T.worklist.title(ui.gp)}</h1>
      <p>${T.worklist.lede(mine.length, fmtDate(data.refDate))}</p>
      <ul class="criteria">${CRITERIA.map((c) => `<li>${c}</li>`)}</ul>
    </section>
    ${data.live ? html`<div class="clock"><b>${T.clock.label(fmtDate(data.live.clock))}</b><span>${T.clock.hint}</span>
      <button type="button" class="btn" data-action="tick">${T.clock.next}</button></div>` : ""}
    <nav class="tiles" aria-label="Stav pacientů">${tiles}</nav>
    ${toolbar}
    <section class="list" aria-live="polite">
      ${rows.length
        ? rows.map((p) => patientRow(p, { composing: ui.composing === p.id, chosenChannel: ui.chosenChannel, plan: data.live?.plans[p.id], link: data.live?.links[p.id] }))
        : `<p class="empty">${T.buckets[ui.bucket].empty}</p>`}
    </section>`;
}
