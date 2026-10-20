// All communication with one patient in one place, newest first:
// what the practice records already had, every message and call we sent (with text and delivery),
// what the patient answered (verbatim) and how it was understood, what the nurse or doctor decided,
// and what the system will do next.
import { CASE, T } from "../case.js";
import { esc, fmtDate } from "../util.js";

const C = T.comm;
const D = T.detail;
const ch = (c) => T.channel[c] || c || "";
const hhmm = (ts) => (ts && ts.length > 10 ? ts.slice(11, 16) : "");
const VIA = { sms: "sms", voice: "voice", "voice-ai": "voice", whatsapp: "whatsapp" }; // link, ui, sim: said in the title
const SIM = "simulovaná odpověď"; // via "sim" (the demo panel, the guided demo); a case overrides it with T.comm.via.sim
const viaLabel = (v) => C.via[v] ?? (v === "sim" ? SIM : "");
let VOICE = {}; // {mode, greeting}: how a live call is held (gather = the stored script; agent = the agent's first sentence)
export const setVoice = (v) => { VOICE = v || {}; };
/** What a live call really said: in agent mode the agent's greeting (the keys-1/2 script was never read out). */
const callText = (m) => (m.channel === "voice" && m.live && VOICE.mode === "agent" && VOICE.greeting ? VOICE.greeting : m.text);

/** The whole call as a dialogue (turns [{who: bot|user, text}] stored with a voice reply). */
export function dialogue(turns, open = false) {
  if (!Array.isArray(turns) || !turns.length) return "";
  const who = { bot: C?.bot || "asistent", user: C?.person || "člověk" };
  return `<details class="dialog"${open ? " open" : ""}><summary>${C?.transcript || "Celý rozhovor"} (${turns.length})</summary><ol class="dialog__t">${turns.map((t) =>
    `<li class="dialog--${t.who === "user" ? "user" : "bot"}"><b>${who[t.who === "user" ? "user" : "bot"]}:</b> ${esc(t.text || "")}</li>`).join("")}</ol></details>`;
}

/** What the call agreed / collected (the recap said back at the end) and whether the person confirmed it. */
export function recapLine(summary, confirmed) {
  if (!summary) return "";
  const mark = confirmed === true ? `<span class="recap__ok">${C?.confirmed || "potvrzeno"}</span>`
    : confirmed === false ? `<span class="recap__no">${C?.notConfirmed || "nepotvrzeno"}</span>` : "";
  return `<p class="recap"><b>${C?.summary || "Shrnutí"}:</b> ${esc(summary)}${mark ? ` ${mark}` : ""}</p>`;
}

/** Timeline items {date, time, actor, channel, title, body, quote, note, status, planned}. */
export function timeline(p, d = {}, plan = null, outbox = null) {
  const items = [];
  for (const h of p.history || []) {
    items.push({ date: h.date, actor: "record", channel: h.channel,
      title: D.msgType[h.type] || h.type, status: D.delivery[h.delivery], fail: h.delivery === "failed" });
    if (h.response && h.response !== "no_response") items.push({ date: h.date, actor: "patient", channel: h.channel, title: D.response[h.response] });
  }
  const live = Array.isArray(outbox);
  for (const m of outbox || []) {
    const st = m.live ? (C.status[m.status] || m.status) : C.simulated;
    items.push({ date: m.day || (m.ts || "").slice(0, 10), time: hhmm(m.ts), actor: m.auto ? "system" : "nurse", channel: m.channel,
      title: C.variant?.[m.variant] || (m.auto ? C.autoSent(m.step) : C.sent), bodyText: callText(m), textLabel: m.channel === "voice" ? C.showScript : C.showText, status: st + (m.duration ? `, ${C.duration(m.duration)}` : ""), fail: ["failed", "undelivered", "no-answer", "busy"].includes(m.status) });
  }
  for (const e of d.journey || []) {
    const isSend = e.stage === CASE.sent_stage && (!e.event || e.event === "send"); // not a reply that keeps the stage
    if (isSend && live) continue; // the outbox has the same send with its text
    if (!e.stage && e.delivery && live) continue; // delivery is already on the outbox item
    if (isSend) { items.push({ date: e.date, actor: e.auto ? "system" : "nurse", channel: e.channel, title: e.auto ? C.autoSent(e.step) : C.sent, status: C.simulated }); continue; }
    if (!e.stage && e.delivery) { items.push({ date: e.date, actor: "system", channel: e.channel, title: D.delivery[e.delivery] || e.delivery, fail: true }); continue; }
    const doctor = e.event === "exclude" || e.event === "include";
    const reply = !!e.text;
    const actor = reply ? "patient" : doctor ? "doctor" : e.auto ? "system" : "nurse";
    let label = C.event[e.event] || D.event[e.stage] || e.event || e.stage;
    if (e.event === "declined" && e.stage === "not_now") label = C.softDeclined; // first refusal is soft, not 01197
    if (e.event === "not_now" && e.via === "ui" && !e.text) label = C.unreachable;
    if (e.event === "booked" && (e.text || (e.via && e.via !== "ui"))) label = T.state.selfBooked(p);
    if (e.event === "booked" && !e.text && e.via === "ui") label = T.state.booked(p);
    items.push({
      date: e.date, actor, channel: reply ? VIA[e.via] : null,
      title: reply ? C.replied(viaLabel(e.via), p) : label + (e.result ? `: ${T.actions.result[e.result].toLowerCase()}` : ""),
      quote: reply ? e.text : null,
      transcript: reply ? e.transcript : null,
      summary: reply ? e.summary : null, confirmed: e.confirmed,
      note: reply ? (e.ignored ? C.ignored : `${C.understood} ${label.toLowerCase()}${e.source === "ai" && e.why ? `. ${e.why}` : ""}`)
        : e.ignored ? C.ignored : "",
      muted: !!e.ignored,
    });
  }
  items.sort((a, b) => (b.date || "").localeCompare(a.date || "") || (b.time || "").localeCompare(a.time || ""));
  if (plan) items.unshift({ date: plan.due, actor: "system", channel: plan.channel, title: C.planned(ch(plan.channel)), planned: true });
  return items;
}

export function comm(p, d, plan, outbox) {
  const items = timeline(p, d, plan, outbox);
  if (!items.length) return `<p>${D.noContacts}</p>`;
  return `<ol class="comm">${items.map((i) => `<li class="comm__i comm--${i.actor}${i.planned ? " is-planned" : ""}${i.fail ? " is-fail" : ""}${i.muted ? " is-muted" : ""}">
    <time>${fmtDate(i.date)}${i.time ? `<small>${i.time}</small>` : ""}</time>
    <i class="comm__mark" aria-hidden="true"></i>
    <div class="comm__body">
      <div class="comm__head"><b>${C.actor[i.actor]}</b>${i.channel ? `<span>${esc(ch(i.channel))}</span>` : ""}${i.status ? `<span class="comm__st">${esc(i.status)}</span>` : ""}</div>
      <div>${esc(i.title)}</div>
      ${i.quote ? `<q>${esc(i.quote)}</q>` : ""}
      ${i.note ? `<div class="muted">${esc(i.note)}</div>` : ""}
      ${recapLine(i.summary, i.confirmed)}${dialogue(i.transcript)}
      ${i.bodyText ? `<details><summary>${i.textLabel}</summary><p>${esc(i.bodyText)}</p></details>` : ""}
    </div></li>`).join("")}</ol>`;
}
