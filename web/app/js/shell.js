// App shell, the same for every case: navigation, views of the case, patient card, click actions, sync with the backend.
// Domain decisions come from the case modules (case.js: dom, rows, cards, VIEWS, ACTIONS).
import { ACTIONS, CASE, T, VIEWS, contentUrl, dataUrl, dom, mineOf } from "./case.js";
import { fmtDate } from "./util.js";
import { store } from "./state.js";
import { api } from "./api.js";
import { loadMessages, message, section } from "./messages.js";
import { loadJourney, refusals, softEvent } from "./fsm.js";
import { card } from "./components/card.js";
import { setVoice } from "./components/comm.js";
import { demoPanel } from "./components/demo.js";
import { scenarioBlock } from "./components/scenario.js";
import { toast, hideToast } from "./components/toast.js";

const POLL_MS = 3000;
const POLL_FAST_MS = 1000; // while a step of the guided demo waits for the visitor's answer (a call in progress)
const ui = { view: VIEWS[0].id, gp: CASE.group?.default ?? null, filter: "all", composing: null, chosenChannel: null, demoReplies: false, open: null };
let data;
let backend = null; // {mode, ai} when served by the backend; null = static page with local simulation
let recipient = null; // demo recipient from /api/recipient (phone and e-mail for live sends)
let seen = -1;
const $ = (id) => document.getElementById(id);

const rowCtx = {
  of: (p) => ({
    composing: ui.composing === p.id, chosenChannel: ui.chosenChannel,
    plan: data.live?.plans[p.id], link: data.live?.links[p.id], demo: ui.demoReplies, open: ui.open === p.id,
    outbox: ui.open === p.id && backend ? outboxCache[p.id] || [] : null,
  }),
};

function render() {
  dom.setClock?.(today());
  const mine = mineOf(data, ui);
  const badge = Object.fromEntries(VIEWS.map((v) => [v.id, v.badge ? v.badge(mine, today(), data.live?.plans) : 0]));
  $("nav").innerHTML = VIEWS.map(({ id: v }) => `<button type="button" data-action="pick-view" data-view="${v}"
    ${ui.view === v ? 'aria-current="page"' : ""}>${T.nav[v]}${badge[v] ? ` <span class="due">${badge[v]}</span>` : ""}</button>`).join("");
  $("view").innerHTML = (VIEWS.find((v) => v.id === ui.view) || VIEWS[0]).render(ui, data, rowCtx);
  renderDemo();
  if (CASE.group) $("gp").value = ui.gp;
  const open = ui.open && find(ui.open);
  const a = document.activeElement; // keep keyboard focus inside the card across re-renders (polling, outbox load)
  const keep = a && a.closest && a.closest("#card") ? a.id || "card-title" : ui.focusCard ? "card-title" : null;
  ui.focusCard = false;
  $("card").innerHTML = open ? card(open, { ...rowCtx.of(open), owner: dom.ownerOf(open, today(), data.live?.plans), lost: dom.lostOf(open, today(), data.live?.plans),
    scenario: data.live?.scenario?.running ? data.live.scenario : null }) : "";
  document.body.classList.toggle("has-card", !!open);
  if (open && keep) document.getElementById(keep)?.focus();
  footer();
}

/** The demo panel alone (the guided demo's countdown refreshes it without re-rendering the views). */
function renderDemo() {
  const typing = document.activeElement?.closest?.("#demo") && document.activeElement.matches("input[type=tel], input[type=email]");
  if (typing) return; // keep what is being typed
  const sc = data.live?.scenario;
  const who = (id) => { const p = id && find(id); return p ? T.who(p) : ""; }; // name of a record a step acted on
  const scenario = backend ? scenarioBlock(sc, section("scenario"), { link: sc && data.live.links[sc.pid], mock: backend.mode !== "live", who }) : "";
  $("demo").innerHTML = demoPanel({ replies: ui.demoReplies, clock: data.live?.clock, fhir: !!backend?.fhir, hall: !!CASE.features?.hall, recipient, recipientError: ui.recipientError, scenario });
}

/** Close the patient card and give focus back to the row that opened it. */
function closeCard(fromHistory = false) {
  const id = ui.open;
  if (!id) return;
  ui.open = null; ui.composing = null;
  if (!fromHistory && history.state?.card) { try { history.back(); } catch { /* ignore */ } }
  render();
  document.querySelector(`#pt-${CSS.escape(id)} .who`)?.focus();
}
let footer = () => {};

const find = (id) => data.patients.find((p) => p.id === id);
const outboxCache = {}; // messages we sent to the open patient (text, delivery), loaded on demand

async function loadOutbox(id) {
  if (!backend || !id) return;
  try { outboxCache[id] = (await api.patient(id)).outbox; } catch { /* keep what we had */ }
}
const today = () => data.live?.clock || data.refDate;

let scnSeen = "";
let scnShown = null; // index of the last guided-demo step whose presentation (view, card) the shell applied; null = not yet seen

/** The guided demo's persona is a record of this visitor only: it comes with the state, not with the data file. */
function personas(list = []) {
  data.patients = [...list, ...data.patients.filter((p) => !p.demo)];
}

/** Open a record's card (the row click and the guided demo). */
function openCard(id) {
  if (!find(id)) return;
  ui.open = id; ui.composing = null;
  try { history.pushState({ card: id }, ""); } catch { /* sandboxed preview */ }
  ui.focusCard = true;
}

/** A step of the guided demo may say where to look: "view" (a view of the case), "card" (true = the persona's card,
 *  false = close it, "other" = the record the step acted on). Applied once, when the step has started. */
function presentScenario(sc) {
  if (!sc?.steps) { scnShown = null; return false; }
  let last = -1;
  sc.steps.forEach((s, i) => { if (s.status !== "pending") last = i; });
  if (scnShown === null) { scnShown = last; return false; } // a reload in the middle: show nothing twice
  if (last <= scnShown) return false;
  scnShown = last;
  const step = sc.steps[last];
  let changed = false;
  if (step.view && VIEWS.some((v) => v.id === step.view) && ui.view !== step.view) { ui.view = step.view; window.scrollTo(0, 0); changed = true; }
  const target = step.card === true ? sc.pid : step.card === "other" ? step.who : null;
  if (target && ui.open !== target && find(target)) { openCard(target); changed = true; }
  else if (step.card === false && ui.open) { ui.open = null; ui.composing = null; changed = true; }
  return changed;
}

async function pull() {
  const s = await api.state();
  const scn = JSON.stringify(s.scenario || null);
  if (s.version === seen && data.live?.clock === s.clock) {
    if (scn !== scnSeen && data.live) { // countdown only, unless a step started and says where to look
      scnSeen = scn; data.live.scenario = s.scenario;
      if (presentScenario(s.scenario)) { await loadOutbox(ui.open); return true; }
      renderDemo();
    }
    return false;
  }
  seen = s.version; scnSeen = scn;
  store.merge(s.decisions);
  personas(s.personas);
  data.live = { clock: s.clock, plans: s.plans || {}, links: s.links || {}, scenario: s.scenario };
  presentScenario(s.scenario);
  if (ui.open) await loadOutbox(ui.open); // delivery and replies of the open patient stay current
  return true;
}

/** Poll faster while the guided demo waits for the visitor (a call rings, runs or is being analysed). */
function pollDelay() {
  const sc = data.live?.scenario;
  return sc?.running && sc.steps?.[sc.step]?.status === "waiting" ? POLL_FAST_MS : POLL_MS;
}

/** Send invitations: through the backend when present (real SMS/calls), otherwise recorded locally. */
async function send(items) {
  if (!backend) return store.send(items, today());
  await api.send(items, today());
  await pull().catch(() => {}); // sent is sent: a failed refresh must not look like a failed send
}

/** Practice decision (skip, draft, override, result acknowledged): local first, then stored on the server. */
async function mark(id, field, value) {
  store.mark(id, field, value);
  if (backend) { await api.mark(id, field, value); await pull().catch(() => {}); }
}

/** Journey step or patient reply: the backend runs the same logic as a real webhook. */
async function step(id, body) {
  if (!backend) {
    return body.text ? store.step(id, body.reply, today(), { via: body.sim ? "sim" : "ui", text: body.text }) : store.step(id, body.stage, today(), body.result ? { result: body.result, via: "ui" } : { via: "ui" });
  }
  await api.step({ id, date: today(), ...body });
  await pull();
}

const actions = {
  "pick-view": (el) => { ui.view = el.dataset.view; ui.composing = null; window.scrollTo(0, 0); },
  "pick-filter": (el) => { ui.filter = el.dataset.filter; ui.composing = null; },
  "open-compose": (el) => { ui.composing = el.dataset.id; ui.chosenChannel = null; },
  "open-card": async (el) => {
    openCard(el.dataset.id); render(); await loadOutbox(ui.open);
  },
  "close-card": (el, e) => closeCard(),
  "pick-channel": (el) => { ui.chosenChannel = el.dataset.channel; },
  "close-compose": () => { ui.composing = null; },
  "save-draft": async (el) => {
    const id = el.dataset.id;
    const text = $(`msg-${id}`)?.value;
    ui.composing = null;
    await mark(id, "skipped", false);
    await mark(id, "draft", { channel: el.dataset.channel, text });
    toast(T.toast.draftSaved, { undo: !backend });
  },
  "confirm-send": async (el) => {
    const p = find(el.dataset.id);
    const text = $(`msg-${p.id}`)?.value;
    ui.composing = null;
    await send([{ id: p.id, channel: el.dataset.channel, variant: dom.plannedContact(p).variant, text }]);
    toast(T.toast.sent(T.channel[el.dataset.channel]), { undo: !backend });
  },
  "approve-batch": async () => {
    const rows = dom.batchOf(mineOf(data, ui));
    await send(rows.map((p) => {
      const { channel, variant } = dom.plannedContact(p);
      const draft = store.get(p.id).draft;
      return { id: p.id, channel, variant, text: draft?.text || message(p, channel, variant) };
    }));
    toast(T.toast.approved(rows.length), { undo: !backend });
  },
  skip: async (el) => { await mark(el.dataset.id, "skipped", true); toast(T.toast.skipped, { undo: !backend }); },
  unskip: async (el) => { await mark(el.dataset.id, "skipped", false); toast(T.toast.unskipped, { undo: !backend }); },
  // Simulated patient reply (via "sim", not an operator's note); with the backend the sample text goes through the real reply understanding.
  reply: async (el) => {
    const r = el.dataset.reply;
    await step(el.dataset.id, { reply: r, text: T.demo.replyText[r], sim: true });
    toast(T.toast.reply(T.demo.reply[r]), { undo: !backend });
  },
  step: async (el) => {
    const { id, stage, result } = el.dataset;
    // The first refusal is soft (journey.json soft_decline; screening: offer again in 3 months), a repeated one is final.
    const soft = stage === softEvent() && refusals(store.get(id).journey) === 0;
    await step(id, { stage, result }); // the state machine decides (first "declined" is soft)
    toast(T.toast.step[soft ? "softDeclined" : stage], { undo: !backend });
  },
  "toggle-replies": (el) => { ui.demoReplies = el.checked; },
  "fhir-sync": async () => { await api.fhirSync(); location.reload(); },
  "recipient-save": async () => {
    const r = await api.setRecipient($("rcp-phone").value, $("rcp-email").value);
    ui.recipientError = r.ok ? "" : r.error;
    if (r.ok) { recipient = r; toast(T.toast.recipientSaved, { undo: false }); }
  },
  "recipient-reset": async () => {
    const r = await api.setRecipient("", "");
    if (r.ok) { recipient = r; ui.recipientError = ""; toast(T.toast.recipientReset, { undo: false }); }
  },
  tick: async () => {
    const r = await api.tick(1);
    await pull();
    toast(T.toast.tick(r.touches.length), { undo: false });
  },
  undo: () => { store.undo(); hideToast(); },
  "scenario-start": async () => {
    await api.scenarioStart();
    seen = -1; scnShown = -1; await pull();
    const p = find(data.live.scenario?.pid);
    if (p && CASE.group) ui.gp = p[CASE.group.field]; // the persona's group, so its row is in every view
    if (p && !ui.open) { openCard(p.id); await loadOutbox(p.id); } // the visitor watches their own card from the first call
    $("demo").open = true;
  },
  "scenario-next": async () => { await api.scenarioNext(); seen = -1; await pull(); },
  "scenario-reset": async () => { await api.scenarioReset(); seen = -1; scnShown = -1; await pull(); if (ui.open && !find(ui.open)) closeCard(); },
  reset: async () => { if (backend) await api.reset(); store.reset(); seen = -1; if (backend) await pull(); hideToast(); },
  "open-practice": (el) => { ui.gp = el.dataset.gp; ui.view = VIEWS[0].id; window.scrollTo(0, 0); },
};

/** What a case action (web/actions.js) may use: `actions = { name: async (el, app) => … }`. */
const app = {
  ui, store, T, toast, send, mark, step, find, today,
  /** A notice about a record through the backend (POST /api/notify), e.g. an SMS to a relative; not a journey step. */
  notify: async (...a) => { const r = await api.notify(...a); await pull(); return r; },
  get data() { return data; },
  get backend() { return backend; }, // null = static page with local simulation
};
for (const [name, fn] of Object.entries(ACTIONS)) actions[name] = (el, e) => fn(el, app, e);

let busy = false; // one real send at a time: a double click must never send twice

async function dispatch(e) {
  const el = e.target.closest("[data-action]");
  if (!el || el.disabled || busy) return;
  if (el.classList.contains("card-wrap") && e.target.closest("[data-stop]")) return; // click inside the card, not the backdrop
  const fn = actions[el.dataset.action];
  if (!fn) return;
  try {
    const pending = fn(el, e);
    if (pending instanceof Promise) {
      busy = true; document.body.setAttribute("aria-busy", "true");
      try { await pending; } finally { busy = false; document.body.removeAttribute("aria-busy"); }
    }
    render();
  } catch {
    busy = false; document.body.removeAttribute("aria-busy");
    toast(T.apiError, { undo: false });
  }
}

async function init() {
  try {
    data = await (await fetch(dataUrl())).json();
  } catch {
    $("view").innerHTML = `<p class="empty">${T.loadError}</p>`;
    return;
  }
  backend = await api.health();
  if (backend) recipient = await api.recipient().catch(() => null); // where live demo messages go
  setVoice({ mode: backend?.voiceMode, greeting: backend?.agentGreeting }); // what a live call really says (agent mode)
  await loadMessages({ withLink: !!backend, trial: !!backend?.trial });
  await loadJourney(contentUrl("journey.json"));
  $("brand").textContent = CASE.brand;
  if (CASE.group) { // e.g. the GP practice: every view shows the records of one group
    const gps = dom.groups(data.patients);
    if (!gps.includes(ui.gp)) ui.gp = gps[0];
    $("group-label").textContent = CASE.group.label;
    $("gp").innerHTML = gps.map((g) => `<option>${g}</option>`).join("");
    $("gp").addEventListener("change", (e) => { ui.gp = e.target.value; ui.composing = null; render(); });
  } else $("group").hidden = true;
  document.addEventListener("click", dispatch);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ui.open) closeCard(); });
  window.addEventListener("popstate", () => { if (ui.open) closeCard(true); });
  document.addEventListener("input", (e) => { // registry search: re-render and keep typing
    if (e.target.id !== "q") return;
    ui.query = e.target.value; render();
    const q = $("q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches("tr[data-action]")) dispatch(e); });
  const d = fmtDate(data.refDate);
  footer = () => { // data date + demo clock + FHIR source, refreshed on every render
    const clk = today() !== data.refDate ? T.footerClock(fmtDate(today())) : "";
    $("foot").textContent = (backend ? T.footerLive(d, backend.mode === "live") : T.footer(d)) + clk + (backend?.fhir ? T.footerFhir(backend.fhir) : "");
  };
  footer();
  $("demo").hidden = false;
  if (backend) {
    await pull().catch(() => {});
    if (data.live?.scenario?.running) $("demo").open = true; // the guided demo goes on after a reload
    // Replies arrive by webhook at any time: refresh, but never while the nurse is editing a message.
    const tick = () => pull().then((changed) => changed && !ui.composing && !busy && render()).catch(() => {})
      .finally(() => setTimeout(tick, pollDelay()));
    setTimeout(tick, pollDelay());
  }
  render();
}

init();
