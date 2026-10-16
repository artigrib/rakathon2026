// Presenter controls, kept apart from the product: simulated replies and (with the backend) the demo clock.
import { T } from "../i18n/cs.js";
import { fmtDate } from "../util.js";

const PALETTES = ["petrol", "orange", "cobalt"];

export function demoPanel({ replies, clock, palette }) {
  return `<summary>${T.demo.title}</summary>
    <div class="demo__body">
      <p>${T.demo.intro}</p>
      ${clock ? `<div><b>${T.demo.clock(fmtDate(clock))}</b></div>
        <button type="button" class="btn" data-action="tick">${T.demo.next}</button>` : ""}
      <label><input type="checkbox" data-action="toggle-replies" ${replies ? "checked" : ""}> ${T.demo.replies}</label>
      <div class="palettes" role="group" aria-label="${T.demo.palette}">${PALETTES.map((k) =>
        `<button type="button" data-action="palette" data-palette="${k}" aria-pressed="${palette === k}"><i class="sw sw--${k}"></i>${T.demo.palettes[k]}</button>`).join("")}</div>
      <button type="button" class="btn btn--link" data-action="reset">${T.demo.reset}</button>
    </div>`;
}
