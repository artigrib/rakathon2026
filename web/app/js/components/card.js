// Record card: one person, one panel (side drawer on desktop, full screen on a phone). Top to bottom, one idea per block:
// who and what now (with the one next action), warnings, the case's facts, journey, all communication, the case's details.
// The case fills its own blocks with web/card.js `blocks(p) → {before, after}` (before the journey, after the communication).
import { T, cards, dom, rows } from "../case.js";
import { esc } from "../util.js";
import { store } from "../state.js";
import { journey } from "./journey.js";
import { comm } from "./comm.js";
import { compose } from "./compose.js";

// A live call of the guided demo, as it happens (outbox entry: Twilio status, `analysing` while the agent's outcome is read).
const CALL_FINAL = ["completed", "no-answer", "busy", "failed", "canceled"];
const CALL = { dialing: "Vytáčíme…", in_progress: "Hovor probíhá…", analysing: "Vyhodnocuji hovor…" }; // core defaults; T.comm.call overrides

const CALL_WHO = { bot: "Asistentka", user: "Senior" }; // core defaults; T.comm.call.who overrides, else T.comm.person
const LIVE_TURNS = 4; // the last turns of a running call shown under the status line

const liveCall = (outbox) => [...(outbox || [])].reverse().find((x) => x.channel === "voice" && x.live);

/** dialing | in_progress | analysing | null for the newest live call of the record. */
export function callState(outbox) {
  const m = liveCall(outbox);
  if (!m) return null;
  if (m.analysing) return "analysing";
  if (CALL_FINAL.includes(m.status)) return null;
  return m.status === "in-progress" ? "in_progress" : "dialing";
}

/** The last turns of the running call (outbox `transcript`: [{who: bot|user, text}], updated while it runs). */
function liveTurns(outbox) {
  const turns = (liveCall(outbox)?.transcript || []).filter((t) => t && t.text).slice(-LIVE_TURNS);
  if (!turns.length) return "";
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const who = { bot: T.comm.call?.who?.bot || CALL_WHO.bot, user: T.comm.call?.who?.user || cap(T.comm.person) || CALL_WHO.user };
  return `<ol class="dialog__t card__live" aria-live="polite">${turns.map((t) => {
    const k = t.who === "user" ? "user" : "bot";
    return `<li class="dialog--${k}"><b>${esc(who[k])}:</b> ${esc(t.text)}</li>`;
  }).join("")}</ol>`;
}

/** scenario: the running guided demo (only then the live call status is shown; the shared demo looks as before). */
export function card(p, { plan, outbox, composing, chosenChannel, owner, lost, scenario = null }) {
  const d = store.get(p.id);
  const C = T.card;
  const { title, sub } = rows.describe(p, d, plan);
  const call = scenario ? callState(outbox) : null;
  const callLine = call ? `<p class="card__call" role="status">${esc(T.comm.call?.[call] || CALL[call])}</p>`
    + (call === "in_progress" || call === "analysing" ? liveTurns(outbox) : "") : "";
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
        ${callLine}
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
