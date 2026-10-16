import { DATA_URL, DEFAULT_GP, POLL_MS } from "./config.js";
import { T } from "./i18n/cs.js";
import { fmtDate } from "./util.js";
import { store } from "./state.js";
import { api } from "./api.js";
import { batchOf, plannedContact, practices } from "./domain.js";
import { loadMessages, message } from "./content/messages.cs.js";
import { worklist } from "./views/worklist.js";
import { overview } from "./views/overview.js";
import { toast, hideToast } from "./components/toast.js";

const ui = { view: "worklist", gp: DEFAULT_GP, bucket: "contact", composing: null, chosenChannel: null };
let data;
let backend = null; // {mode: "live" | "mock"} when served by the backend, else null (static page, local simulation)
let seen = -1;
const $ = (id) => document.getElementById(id);

function render() {
  $("view").innerHTML = ui.view === "worklist" ? worklist(ui, data) : overview(data);
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === ui.view));
  $("gp").value = ui.gp;
}

const find = (id) => data.patients.find((p) => p.id === id);
const today = () => data.live?.clock || data.refDate;

async function pull() {
  const s = await api.state();
  if (s.version === seen && data.live?.clock === s.clock) return false;
  seen = s.version;
  store.merge(s.decisions);
  data.live = { clock: s.clock, plans: s.plans || {}, links: s.links || {} };
  return true;
}

/** Send invitations: through the backend when present (real SMS/calls), otherwise recorded locally. */
async function send(items) {
  if (!backend) return store.send(items, today());
  await api.send(items, today());
  await pull();
}

/** Journey step or patient reply: backend runs the same logic as a real webhook. */
async function step(id, body) {
  if (!backend) {
    return body.text ? store.step(id, body.reply, today()) : store.step(id, body.stage, today(), body.result ? { result: body.result } : {});
  }
  await api.step({ id, date: today(), ...body });
  await pull();
}

const actions = {
  "pick-view": (el) => { ui.view = el.dataset.view; ui.composing = null; },
  "pick-bucket": (el) => { ui.bucket = el.dataset.bucket; ui.composing = null; },
  "open-compose": (el) => { ui.composing = el.dataset.id; ui.chosenChannel = null; },
  "pick-channel": (el) => { ui.chosenChannel = el.dataset.channel; },
  "close-compose": () => { ui.composing = null; },
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
      return { id: p.id, channel, variant, text: message(p, channel, variant) };
    }));
    toast(T.toast.approved(rows.length), { undo: !backend });
  },
  skip: (el) => { store.skip(el.dataset.id); toast(T.toast.skipped); },
  unskip: (el) => { store.skip(el.dataset.id, false); toast(T.toast.unskipped); },
  // Simulated patient reply; in live mode the sample text goes through the real reply classifier.
  reply: async (el) => {
    const r = el.dataset.reply;
    await step(el.dataset.id, { reply: r, text: T.journey.replyText[r] });
    toast(T.toast.reply(T.journey.replies[r]), { undo: !backend });
  },
  step: async (el) => {
    const { id, stage, result } = el.dataset;
    await step(id, { stage, result });
    toast(T.toast.step[stage], { undo: !backend });
  },
  include: (el) => { store.include(el.dataset.id); toast(el.dataset.exception ? T.toast.exception : T.toast.included); },
  exclude: (el) => { store.exclude(el.dataset.id); toast(T.toast.excluded); },
  tick: async () => {
    const r = await api.tick(1);
    await pull();
    toast(T.toast.tick(r.touches.length), { undo: false });
  },
  undo: () => { store.undo(); hideToast(); },
  reset: async () => { if (backend) await api.reset(); store.reset(); seen = -1; hideToast(); },
  "open-practice": (el) => { ui.gp = el.dataset.gp; ui.view = "worklist"; ui.bucket = "contact"; },
};

async function dispatch(e) {
  const el = e.target.closest("[data-action]");
  if (!el || el.disabled) return;
  const fn = actions[el.dataset.action];
  if (!fn) return;
  try {
    const pending = fn(el);
    render();
    if (pending instanceof Promise) { await pending; render(); }
  } catch {
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
  await loadMessages({ withLink: !!backend });
  const gps = practices(data.patients);
  if (!gps.includes(ui.gp)) ui.gp = gps[0];
  $("gp").innerHTML = gps.map((g) => `<option>${g}</option>`).join("");
  $("gp").addEventListener("change", (e) => { ui.gp = e.target.value; ui.view = "worklist"; ui.bucket = "contact"; ui.composing = null; render(); });
  document.addEventListener("click", dispatch);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches("tr[data-action]")) dispatch(e); });
  const d = fmtDate(data.refDate);
  $("foot").textContent = backend ? T.footerLive(d, backend.mode === "live", backend.ai) : T.footer(d);
  if (backend) {
    await pull().catch(() => {});
    // Replies arrive by webhook at any time: refresh, but never while the nurse is editing a message.
    setInterval(() => pull().then((changed) => changed && !ui.composing && render()).catch(() => {}), POLL_MS);
  }
  render();
}

init();
