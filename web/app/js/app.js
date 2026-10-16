import { DATA_URL, DEFAULT_GP, POLL_MS } from "./config.js";
import { T } from "./i18n/cs.js";
import { fmtDate } from "./util.js";
import { store } from "./state.js";
import { api } from "./api.js";
import { batchOf, plannedContact, practices } from "./domain.js";
import { loadMessages, message } from "./content/messages.cs.js";
import { tasks, taskCount } from "./views/tasks.js";
import { patients } from "./views/patients.js";
import { overview } from "./views/overview.js";
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
  }),
};

function render() {
  const mine = data.patients.filter((p) => p.gp === ui.gp);
  const due = taskCount(mine);
  $("nav").innerHTML = ["tasks", "patients", "overview"].map((v) => `<button type="button" data-action="pick-view" data-view="${v}"
    ${ui.view === v ? 'aria-current="page"' : ""}>${T.nav[v]}${v === "tasks" && due ? ` <span class="due">${due}</span>` : ""}</button>`).join("");
  $("view").innerHTML = ui.view === "tasks" ? tasks(ui, data, rowCtx) : ui.view === "patients" ? patients(ui, data, rowCtx) : overview(data);
  $("demo").innerHTML = demoPanel({ replies: ui.demoReplies, clock: data.live?.clock });
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
  await pull().catch(() => {}); // sent is sent: a failed refresh must not look like a failed send
}

/** Journey step or patient reply: the backend runs the same logic as a real webhook. */
async function step(id, body) {
  if (!backend) {
    return body.text ? store.step(id, body.reply, today()) : store.step(id, body.stage, today(), body.result ? { result: body.result } : {});
  }
  await api.step({ id, date: today(), ...body });
  await pull();
}

const actions = {
  "pick-view": (el) => { ui.view = el.dataset.view; ui.composing = null; window.scrollTo(0, 0); },
  "pick-filter": (el) => { ui.filter = el.dataset.filter; ui.composing = null; },
  "open-compose": (el) => { ui.composing = el.dataset.id; ui.chosenChannel = null; },
  "toggle-detail": (el) => { ui.open = ui.open === el.dataset.id ? null : el.dataset.id; },
  "pick-channel": (el) => { ui.chosenChannel = el.dataset.channel; },
  "close-compose": () => { ui.composing = null; },
  "save-draft": (el) => {
    const id = el.dataset.id;
    store.draft(id, el.dataset.channel, $(`msg-${id}`)?.value);
    ui.composing = null;
    toast(T.toast.draftSaved, { undo: true });
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
  skip: (el) => { store.skip(el.dataset.id); toast(T.toast.skipped); },
  unskip: (el) => { store.skip(el.dataset.id, false); toast(T.toast.unskipped); },
  // Simulated patient reply; with the backend the sample text goes through the real reply understanding.
  reply: async (el) => {
    const r = el.dataset.reply;
    await step(el.dataset.id, { reply: r, text: T.demo.replyText[r] });
    toast(T.toast.reply(T.demo.reply[r]), { undo: !backend });
  },
  step: async (el) => {
    const { id, stage, result } = el.dataset;
    // Doctor: the first "no" is soft (offer again in 3 months), a repeated one is the refusal 01197.
    const soft = stage === "declined" && !(store.get(id).journey || []).some((e) => e.intent === "declined" || e.stage === "declined");
    if (soft && !backend) store.step(id, "not_now", today(), { intent: "declined" });
    else await step(id, { stage, result });
    toast(T.toast.step[soft ? "softDeclined" : stage], { undo: !backend });
  },
  include: (el) => { store.include(el.dataset.id); toast(el.dataset.exception ? T.toast.exception : T.toast.included); },
  exclude: (el) => { store.exclude(el.dataset.id); toast(T.toast.excluded); },
  "toggle-replies": (el) => { ui.demoReplies = el.checked; },
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
  const gps = practices(data.patients);
  if (!gps.includes(ui.gp)) ui.gp = gps[0];
  $("gp").innerHTML = gps.map((g) => `<option>${g}</option>`).join("");
  $("gp").addEventListener("change", (e) => { ui.gp = e.target.value; ui.composing = null; render(); });
  document.addEventListener("click", dispatch);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches("tr[data-action]")) dispatch(e); });
  const d = fmtDate(data.refDate);
  $("foot").textContent = backend ? T.footerLive(d, backend.mode === "live") : T.footer(d);
  $("demo").hidden = false;
  if (backend) {
    await pull().catch(() => {});
    // Replies arrive by webhook at any time: refresh, but never while the nurse is editing a message.
    setInterval(() => pull().then((changed) => changed && !ui.composing && !busy && render()).catch(() => {}), POLL_MS);
  }
  render();
}

init();
