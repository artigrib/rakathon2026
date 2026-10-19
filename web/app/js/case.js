// The active case (cases/<id>/, see cases/README.md): its manifest, strings, config and domain functions.
// Loaded once by app.js before anything else, so every other module can use these bindings at import time.
//
// Served by the backend: manifest /api/case, JSON /app/content/<name>, case modules /app/case/<path>.
// As a static page (serve the repo root with any web server, open /web/app/?case=<id>): straight from ../../cases/<id>/.
// Case modules import core modules by the bare prefix "core/" (import map in index.html), e.g. "core/state.js".

export let CASE = null;  // case.json
export let T = null;     // web/i18n.js:   export const T = {…}
export let cfg = null;   // web/config.js: CHANNELS, REPLIES, JOURNEY, FILTERS, PRACTICES …
export let dom = null;   // web/domain.js: stageOf, ownerOf, lostOf, plannedContact, batchOf, failedChannels, groups …
export let rows = null;  // web/row.js:    describe(p, d, plan), actions(p, d), rowClass(p, d)?
export let cards = null; // web/card.js:   blocks(p) → {before, after}   (optional)
export let VIEWS = [];   // [{id, render(ui, data, rowCtx), badge(mine, clock, plans)?}] in manifest order
export let ACTIONS = {}; // web/actions.js: export const actions = {name: async (el, app) => …}   (optional)
export let STATIC = false;

let base = { content: "content/", web: "case/", data: "data/patients.json" };
const abs = (path) => new URL(path, document.baseURI).href;

/** URL of a JSON file of the case (journey.json, messages.cs.json …). */
export const contentUrl = (name) => abs(base.content + name);
/** URL of the case's records ({refDate, patients: […]}). */
export const dataUrl = () => abs(base.data);
/** Records of the selected group (e.g. the practice); all records when the case has no groups. */
export const mineOf = (data, ui) => (CASE.group ? data.patients.filter((p) => p[CASE.group.field] === ui.gp) : data.patients);

async function optional(url) {
  try { return await import(url); } catch (e) { console.debug("case module not loaded:", url, e); return {}; }
}

export async function loadCase() {
  let manifest = null;
  try {
    const r = await fetch("/api/case");
    if (r.status === 401) { location.href = "/login?next=/app/"; return new Promise(() => {}); }
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) manifest = await r.json();
  } catch { /* no backend */ }
  if (!manifest) { // static page: the case package straight from the repository
    STATIC = true;
    const id = new URLSearchParams(location.search).get("case") || "screening";
    const root = `../../cases/${id}/`;
    manifest = await (await fetch(abs(root + "case.json"))).json();
    base = { content: root, web: `${root}web/`, data: `../../${manifest.data}` };
  }
  CASE = manifest;
  // Order matters: strings and config first, the modules that use them at import time after.
  T = (await import(abs(base.web + "i18n.js"))).T;
  cfg = await import(abs(base.web + "config.js"));
  dom = await import(abs(base.web + "domain.js"));
  rows = await import(abs(base.web + "row.js"));
  cards = await optional(abs(base.web + "card.js"));
  ACTIONS = (await optional(abs(base.web + "actions.js"))).actions || {};
  VIEWS = [];
  for (const v of CASE.views) {
    const m = await import(v.module.startsWith("core/") ? v.module : abs(base.web + v.module));
    VIEWS.push({ id: v.id, render: m.render, badge: m.badge });
  }
  return CASE;
}
