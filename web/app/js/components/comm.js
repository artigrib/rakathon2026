// All communication with one patient in one place, newest first:
// what the practice records already had, every message and call we sent (with text and delivery),
// what the patient answered (verbatim) and how it was understood, what the nurse or doctor decided,
// and what the system will do next.
import { T } from "../i18n/cs.js";
import { esc, fmtDate } from "../util.js";

const C = T.comm;
const D = T.detail;
const ch = (c) => T.channel[c] || c || "";
const hhmm = (ts) => (ts && ts.length > 10 ? ts.slice(11, 16) : "");
const VIA = { sms: "sms", voice: "voice", "voice-ai": "voice", whatsapp: "whatsapp" }; // link and ui: said in the title

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
      title: m.auto ? C.autoSent(m.step) : C.sent, bodyText: m.text, textLabel: m.channel === "voice" ? C.showScript : C.showText, status: st + (m.duration ? `, ${C.duration(m.duration)}` : ""), fail: ["failed", "undelivered", "no-answer", "busy"].includes(m.status) });
  }
  for (const e of d.journey || []) {
    if (e.stage === "sent" && live) continue; // the outbox has the same send with its text
    if (!e.stage && e.delivery && live) continue; // delivery is already on the outbox item
    if (e.stage === "sent") { items.push({ date: e.date, actor: e.auto ? "system" : "nurse", channel: e.channel, title: e.auto ? C.autoSent(e.step) : C.sent, status: C.simulated }); continue; }
    if (!e.stage && e.delivery) { items.push({ date: e.date, actor: "system", channel: e.channel, title: D.delivery[e.delivery] || e.delivery, fail: true }); continue; }
    const doctor = e.event === "exclude" || e.event === "include";
    const reply = !!e.text;
    const actor = reply ? "patient" : doctor ? "doctor" : e.auto ? "system" : "nurse";
    const label = C.event[e.event] || D.event[e.stage] || e.event || e.stage;
    items.push({
      date: e.date, actor, channel: reply ? VIA[e.via] : null,
      title: reply ? C.replied(C.via[e.via] || "") : label + (e.result ? `: ${T.actions.result[e.result].toLowerCase()}` : ""),
      quote: reply ? e.text : null,
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
      ${i.bodyText ? `<details><summary>${i.textLabel}</summary><p>${esc(i.bodyText)}</p></details>` : ""}
    </div></li>`).join("")}</ol>`;
}
