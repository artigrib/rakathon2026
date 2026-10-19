// Entry point: load the active case first (manifest, strings, its modules), then the app shell that uses them.
import { CASE, loadCase } from "./case.js";

try {
  await loadCase();
  document.title = CASE.title;
  document.documentElement.lang = CASE.lang || "cs";
  await import("./shell.js");
} catch (e) { // a case module that fails to load or throws at import time: say so instead of a blank page
  console.error("case failed to load", e);
  const p = document.createElement("pre");
  p.style.cssText = "margin:2rem;white-space:pre-wrap;color:#a00";
  p.textContent = `The case could not be loaded: ${e?.message || e}`;
  document.body.prepend(p);
}
