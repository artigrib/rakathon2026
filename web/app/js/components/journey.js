import { T, cfg } from "../case.js";

/** Index of the reached journey step (-1 = not started yet). config JOURNEY = [{key, stages: […]}]. */
export const journeyIndex = (stage) => cfg.JOURNEY.findIndex((j) => j.stages.includes(stage));

/** Journey as words: done steps in ink, the current one underlined in red, the rest grey. */
export function journey(stage) {
  const at = journeyIndex(stage);
  if (at < 0) return "";
  return `<ol class="steps" aria-label="${T.detail.journey}">${cfg.JOURNEY.map((j, i) =>
    `<li class="${i < at ? "done" : i === at ? "now" : ""}"${i === at ? ' aria-current="step"' : ""}><span>${T.journey.steps[j.key]}</span></li>`).join("")}</ol>`;
}
