// Record card: one person, one panel (side drawer on desktop, full screen on a phone). Top to bottom, one idea per block:
// who and what now (with the one next action), warnings, the case's facts, journey, all communication, the case's details.
// The case fills its own blocks with web/card.js `blocks(p) → {before, after}` (before the journey, after the communication).
import { T, cards, dom, rows } from "../case.js";
import { esc } from "../util.js";
import { store } from "../state.js";
import { journey } from "./journey.js";
import { comm } from "./comm.js";
import { compose } from "./compose.js";

export function card(p, { plan, outbox, composing, chosenChannel, owner, lost }) {
  const d = store.get(p.id);
  const C = T.card;
  const { title, sub } = rows.describe(p, d, plan);
  const warnings = (p.flags || []).filter((f) => f.sev === "warning");
  const path = journey(dom.stageOf(p));
  const why = lost ? T.lost[lost.code](lost.days, p) : "";
  const { before = "", after = "" } = cards.blocks ? cards.blocks(p) : {};
  return `<div class="card-wrap" data-action="close-card">
    <section class="card" role="dialog" aria-modal="true" aria-labelledby="card-title" data-stop>
      <header class="card__head">
        <div>
          <h2 id="card-title" tabindex="-1">${esc(T.who(p))}</h2>
          ${owner ? `<p class="card__owner">${C.owner[owner]}</p>` : ""}
        </div>
        <button type="button" class="card__close" data-action="close-card" aria-label="${C.close}">✕</button>
      </header>
      <div class="card__now">
        ${why ? `<em class="lostwhy">${esc(why)}</em>` : ""}
        <b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}
        <div class="actions">${rows.actions(p, d)}</div>
        ${composing ? compose(p, chosenChannel) : ""}
      </div>
      ${warnings.length ? `<ul class="warn">${warnings.map((f) => `<li>${esc(f.text)}</li>`).join("")}</ul>` : ""}
      ${before}
      ${path ? `<section class="card__block"><h3>${T.detail.journey}</h3>${path}</section>` : ""}
      <section class="card__block"><h3>${T.comm.title}</h3>${comm(p, d, plan, outbox)}</section>
      ${after}
    </section>
  </div>`;
}
