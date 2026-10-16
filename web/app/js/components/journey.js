import { JOURNEY } from "../config.js";
import { T } from "../i18n/cs.js";
import { journeyIndex } from "../domain.js";

/** Journey as words: done steps in ink, the current one underlined in red, the rest grey. */
export function journey(stage) {
  const at = journeyIndex(stage);
  if (at < 0) return "";
  return `<ol class="steps" aria-label="${T.detail.journey}">${JOURNEY.map((j, i) =>
    `<li class="${i < at ? "done" : i === at ? "now" : ""}"${i === at ? ' aria-current="step"' : ""}><span>${T.journey.steps[j.key]}</span></li>`).join("")}</ol>`;
}
