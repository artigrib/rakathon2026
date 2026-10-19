// Entry point: load the active case first (manifest, strings, its modules), then the app shell that uses them.
import { CASE, loadCase } from "./case.js";

await loadCase();
document.title = CASE.title;
document.documentElement.lang = CASE.lang || "cs";
await import("./shell.js");
