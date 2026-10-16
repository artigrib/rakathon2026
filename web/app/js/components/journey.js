import { JOURNEY } from "../config.js";
import { T } from "../i18n/cs.js";
import { journeyIndex } from "../domain.js";

/** Five-step journey strip: done steps filled, current step marked, rest outlined. */
export function journey(stage) {
  const at = journeyIndex(stage);
  if (at < 0) return "";
  return `<ol class="steps" aria-label="Cesta pacienta">${JOURNEY.map((j, i) =>
    `<li class="${i < at ? "done" : i === at ? "now" : ""}"${i === at ? ' aria-current="step"' : ""}>${T.journey.steps[j.key]}</li>`).join("")}</ol>`;
}
