// Presenter controls, kept apart from the product: simulated replies and (with the backend) the demo clock.
import { T } from "../i18n/cs.js";
import { fmtDate } from "../util.js";

export function demoPanel({ open, replies, clock }) {
  return `<summary>${T.demo.title}</summary>
    <div class="demo__body">
      <p>${T.demo.intro}</p>
      ${clock ? `<div><b>${T.demo.clock(fmtDate(clock))}</b></div>
        <button type="button" class="btn" data-action="tick">${T.demo.next}</button>` : ""}
      <label><input type="checkbox" data-action="toggle-replies" ${replies ? "checked" : ""}> ${T.demo.replies}</label>
      <button type="button" class="btn btn--link" data-action="reset">${T.demo.reset}</button>
    </div>`;
}
