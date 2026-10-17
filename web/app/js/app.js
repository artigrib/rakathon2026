import { DATA_URL, DEFAULT_GP, POLL_MS } from "./config.js";
import { T } from "./i18n/cs.js";
import { fmtDate } from "./util.js";
import { store } from "./state.js";
import { api } from "./api.js";
import { batchOf, plannedContact, practices } from "./domain.js";
import { loadMessages, message } from "./content/messages.cs.js";
import { loadJourney, refusals } from "./fsm.js";
import { tasks, taskCount } from "./views/tasks.js";
import { patients } from "./views/patients.js";
import { overview } from "./views/overview.js";
import { doctor, doctorCount } from "./views/doctor.js";
import { card } from "./components/card.js";
import { lostOf, ownerOf } from "./domain.js";
import { demoPanel } from "./components/demo.js";
import { toast, hideToast } from "./components/toast.js";

const ui = { view: "tasks", gp: DEFAULT_GP, filter: "all", composing: null, chosenChannel: null, demoReplies: false, open: null };
let data;
let backend = null; // {mode, ai} when served by the backend; null = static page with local simulation
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
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const due = taskCount(mine, today(), data.live?.plans);
  const docDue = doctorCount(mine, today(), data.live?.plans);
  const badge = { tasks: due, doctor: docDue };
  $("nav").innerHTML = ["tasks", "doctor", "patients", "overview"].map((v) => `<button type="button" data-action="pick-view" data-view="${v}"
    ${ui.view === v ? 'aria-current="page"' : ""}>${T.nav[v]}${badge[v] ? ` <span class="due">${badge[v]}</span>` : ""}</button>`).join("");
  $("view").innerHTML = ui.view === "tasks" ? tasks(ui, data, rowCtx) : ui.view === "doctor" ? doctor(ui, data, rowCtx)
    : ui.view === "patients" ? patients(ui, data, rowCtx) : overview(data);
  $("demo").innerHTML = demoPanel({ replies: ui.demoReplies, clock: data.live?.clock, fhir: !!backend?.fhir });
  $("gp").value = ui.gp;
  const open = ui.open && find(ui.open);
  const a = document.activeElement; // keep keyboard focus inside the card across re-renders (polling, outbox load)
  const keep = a && a.closest && a.closest("#card") ? a.id || "card-title" : ui.focusCard ? "card-title" : null;
  ui.focusCard = false;
  $("card").innerHTML = open ? card(open, { ...rowCtx.of(open), owner: ownerOf(open, today(), data.live?.plans), lost: lostOf(open, today(), data.live?.plans) }) : "";
  document.body.classList.toggle("has-card", !!open);
  if (open && keep) document.getElementById(keep)?.focus();
  footer();
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

async function pull() {
  const s = await api.state();
  if (s.version === seen && data.live?.clock === s.clock) return false;
  seen = s.version;
  store.merge(s.decisions);
  data.live = { clock: s.clock, plans: s.plans || {}, links: s.links || {} };
  if (ui.open) await loadOutbox(ui.open); // delivery and replies of the open patient stay current
  return true;
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
    return body.text ? store.step(id, body.reply, today(), { via: "ui", text: body.text }) : store.step(id, body.stage, today(), body.result ? { result: body.result, via: "ui" } : { via: "ui" });
  }
  await api.step({ id, date: today(), ...body });
  await pull();
}

const actions = {
  "pick-view": (el) => { ui.view = el.dataset.view; ui.composing = null; window.scrollTo(0, 0); },
  "pick-filter": (el) => { ui.filter = el.dataset.filter; ui.composing = null; },
  "open-compose": (el) => { ui.composing = el.dataset.id; ui.chosenChannel = null; },
  "open-card": async (el) => {
    ui.open = el.dataset.id; ui.composing = null;
    try { history.pushState({ card: ui.open }, ""); } catch { /* sandboxed preview */ }
    ui.focusCard = true; render(); await loadOutbox(ui.open);
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
    await send([{ id: p.id, channel: el.dataset.channel, variant: plannedContact(p).variant, text }]);
    toast(T.toast.sent(T.channel[el.dataset.channel]), { undo: !backend });
  },
  "approve-batch": async () => {
    const rows = batchOf(data.patients.filter((p) => p.gp === ui.gp));
    await send(rows.map((p) => {
      const { channel, variant } = plannedContact(p);
      const draft = store.get(p.id).draft;
      return { id: p.id, channel, variant, text: draft?.text || message(p, channel, variant) };
    }));
    toast(T.toast.approved(rows.length), { undo: !backend });
  },
  skip: async (el) => { await mark(el.dataset.id, "skipped", true); toast(T.toast.skipped, { undo: !backend }); },
  unskip: async (el) => { await mark(el.dataset.id, "skipped", false); toast(T.toast.unskipped, { undo: !backend }); },
  ack: async (el) => { await mark(el.dataset.id, "resultAck", true); toast(T.toast.ack, { undo: !backend }); },
  // Simulated patient reply; with the backend the sample text goes through the real reply understanding.
  reply: async (el) => {
    const r = el.dataset.reply;
    await step(el.dataset.id, { reply: r, text: T.demo.replyText[r] });
    toast(T.toast.reply(T.demo.reply[r]), { undo: !backend });
  },
  step: async (el) => {
    const { id, stage, result } = el.dataset;
    // Doctor: the first "no" is soft (offer again in 3 months), a repeated one is the refusal 01197.
    const soft = stage === "declined" && refusals(store.get(id).journey) === 0;
    await step(id, { stage, result }); // the state machine decides (first "declined" is soft)
    toast(T.toast.step[soft ? "softDeclined" : stage], { undo: !backend });
  },
  include: async (el) => {
    const id = el.dataset.id;
    if (store.get(id).override === "EXCLUDED" || store.get(id).stage === "excluded") await step(id, { stage: "include" });
    await mark(id, "override", "ELIGIBLE"); toast(el.dataset.exception ? T.toast.exception : T.toast.included, { undo: !backend });
  },
  exclude: async (el) => { await step(el.dataset.id, { stage: "exclude" }); await mark(el.dataset.id, "override", "EXCLUDED"); toast(T.toast.excluded, { undo: !backend }); },
  "toggle-replies": (el) => { ui.demoReplies = el.checked; },
  "fhir-sync": async () => { await api.fhirSync(); location.reload(); },
  tick: async () => {
    const r = await api.tick(1);
    await pull();
    toast(T.toast.tick(r.touches.length), { undo: false });
  },
  undo: () => { store.undo(); hideToast(); },
  reset: async () => { if (backend) await api.reset(); store.reset(); seen = -1; if (backend) await pull(); hideToast(); },
  "open-practice": (el) => { ui.gp = el.dataset.gp; ui.view = "tasks"; window.scrollTo(0, 0); },
};

let busy = false; // one real send at a time: a double click must never send twice

async function dispatch(e) {
  const el = e.target.closest("[data-action]");
  if (!el || el.disabled || busy) return;
  if (el.classList.contains("card-wrap") && e.target.closest("[data-stop]")) return; // click inside the card, not the backdrop
  const fn = actions[el.dataset.action];
  if (!fn) return;
  try {
    const pending = fn(el);
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
    data = await (await fetch(DATA_URL)).json();
  } catch {
    $("view").innerHTML = `<p class="empty">${T.loadError}</p>`;
    return;
  }
  backend = await api.health();
  await loadMessages({ withLink: !!backend, trial: !!backend?.trial });
  await loadJourney();
  const gps = practices(data.patients);
  if (!gps.includes(ui.gp)) ui.gp = gps[0];
  $("gp").innerHTML = gps.map((g) => `<option>${g}</option>`).join("");
  $("gp").addEventListener("change", (e) => { ui.gp = e.target.value; ui.composing = null; render(); });
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
    // Replies arrive by webhook at any time: refresh, but never while the nurse is editing a message.
    setInterval(() => pull().then((changed) => changed && !ui.composing && !busy && render()).catch(() => {}), POLL_MS);
  }
  render();
}

init();
