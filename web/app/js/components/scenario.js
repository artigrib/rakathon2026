// Guided demo ("Spustit celou ukázku"): the whole case on the visitor's own phone. Generic: the steps and their
// progress come from /api/state (backend/scenario.py), the words from the case's messages.cs.json "scenario".
import { esc } from "../util.js";

const fill = (t, v) => t.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));

/** sc = state.scenario, S = texts, link = relative /p/… of the persona, mock = the backend sends nothing for real. */
export function scenarioBlock(sc, S, { link, mock }) {
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
    return `<li class="scn__i scn__i--${esc(s.status)}${cur ? " scn__i--cur" : ""}"${cur ? ' aria-current="step"' : ""}>
      <span class="scn__t">${esc(t.title)}</span> <span class="scn__st">${esc(st)}</span>${left}
      ${cur ? `<p class="scn__look">${esc(t.look)}</p>` : ""}
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
