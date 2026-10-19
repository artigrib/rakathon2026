// Guided demo ("Spustit celou ukázku"): the whole case on the visitor's own phone. Generic: the steps and their
// progress come from /api/state (backend/scenario.py), the words from the case's messages.cs.json "scenario".
// A step may carry its own extras (scenario.json): "text" (a paragraph, {who} = the record it acted on),
// "while_waiting" ({title, text, bullets}) shown while it waits, and "call" (dialing | in_progress | analysing | over),
// the state of its live call.
import { esc } from "../util.js";

const fill = (t, v) => t.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
// core defaults; a case overrides them in messages.cs.json scenario.call
const CALL = { dialing: "Vytáčíme…", in_progress: "Hovor probíhá…", analysing: "Vyhodnocuji hovor…" };

function waiting(w) {
  if (!w) return "";
  const bullets = (w.bullets || []).map((b) => `<li>${esc(b)}</li>`).join("");
  return `<div class="scn__wait">${w.title ? `<b>${esc(w.title)}</b>` : ""}${w.text ? `<p>${esc(w.text)}</p>` : ""}
    ${bullets ? `<ul class="scn__rules">${bullets}</ul>` : ""}</div>`;
}

/** sc = state.scenario, S = texts, link = relative /p/… of the persona, mock = the backend sends nothing for real,
 *  who(id) = display name of a record (for {who} in a step's text). */
export function scenarioBlock(sc, S, { link, mock, who = () => "" }) {
  if (!sc || !S) return "";
  if (!sc.available) return `<div class="scn"><b>${esc(S.title)}</b><p class="demo__hint">${esc(S.unavailable)}</p></div>`;
  const facts = (S.facts || []).map((f) => `<p class="scn__fact">${esc(f)}</p>`).join("");
  if (!sc.steps) {
    return `<div class="scn"><b>${esc(S.title)}</b><p>${esc(S.intro)}</p>${facts}
      ${mock ? `<p class="demo__hint">${esc(S.mock)}</p>` : ""}
      <button type="button" class="btn btn--primary scn__start" data-action="scenario-start">${esc(S.start)}</button></div>`;
  }
  const items = sc.steps.map((s, i) => {
    const t = S.steps[s.id] || { title: s.id, look: "" };
    const cur = sc.running && i === sc.step;
    const st = cur && s.status === "pending" ? S.now : S.status[s.status] || s.status;
    const left = cur && sc.left ? ` <span class="scn__left">${esc(fill(S.left, { s: sc.left }))}</span>` : "";
    const call = cur && s.status === "waiting" && s.call && s.call !== "over" ? (S.call?.[s.call] || CALL[s.call]) : "";
    const text = s.text && s.status !== "pending" && (!s.text.includes("{who}") || s.who) ? `<p class="scn__text">${esc(fill(s.text, { who: who(s.who) }))}</p>` : "";
    return `<li class="scn__i scn__i--${esc(s.status)}${cur ? " scn__i--cur" : ""}"${cur ? ' aria-current="step"' : ""}>
      <span class="scn__t">${esc(t.title)}</span> <span class="scn__st">${esc(st)}</span>${left}
      ${cur ? `<p class="scn__look">${esc(t.look)}</p>` : ""}
      ${call ? `<p class="scn__call" role="status">${esc(call)}</p>` : ""}
      ${text}
      ${cur && s.status === "waiting" ? waiting(s.while_waiting) : ""}
      ${s.note && S.note[s.note] ? `<p class="demo__err">${esc(S.note[s.note])}</p>` : ""}</li>`;
  }).join("");
  return `<div class="scn"><b>${esc(S.title)}</b>${facts}
    ${mock ? `<p class="demo__hint">${esc(S.mock)}</p>` : ""}
    <ol class="scn__list">${items}</ol>
    ${sc.finished ? `<p class="scn__done" role="status">${esc(S.finished)}</p>` : ""}
    <div class="demo__row">
      ${sc.running ? `<button type="button" class="btn btn--primary" data-action="scenario-next">${esc(S.next)}</button>` : ""}
      <button type="button" class="btn" data-action="open-card" data-id="${esc(sc.pid)}">${esc(S.openCard)}</button>
      ${link ? `<a class="btn" href="${esc(link)}" target="_blank" rel="noopener">${esc(S.openLink)}</a>` : ""}
    </div>
    <div class="demo__row">
      ${sc.finished ? `<button type="button" class="btn" data-action="scenario-start">${esc(S.restart)}</button>` : ""}
      <button type="button" class="btn btn--link" data-action="scenario-reset">${esc(S.reset)}</button>
    </div></div>`;
}
