// Blocks of the senior's card (core/components/card.js). Order of reading, one idea per block:
// what to do now (core card__now) → what the last call left to do (emergency SMS for the relative, crisis lines; hooks.py)
// → the relative (tel: link, "Zavolat příbuznému") → open needs → the last three calls
// → facts and notes a hook may have stored → [core: journey, communication] → the rest under "Více" (mood chart, all calls)
// → the simulated answer of the demo (only here, not in the rows: case.json "row_demo": false).
import { T } from "./i18n.js";
import { cfg } from "core/case.js";
import { esc, fmtDate } from "core/util.js";
import { store } from "core/state.js";
import { allowed } from "core/fsm.js";
import { btn } from "core/components/row.js";
import { dialogue, recapLine } from "core/components/comm.js";
import { callsOf, itemLabel, moodSeries, openNeeds, stageDate, stageOf } from "./domain.js";
import { chips, moodBadge, moodChart } from "./ui.js";

const C = T.card;

const telLink = (phone) => {
  const tel = (phone || "").replace(/\s/g, "");
  return tel ? `<a href="tel:${esc(tel)}">${esc(phone)}</a>` : "";
};

function facts(p) {
  const s = p.schedule;
  const rows = [ // [label, text] escaped, or [label, html, true]
    [C.age, `${p.age} let`],
    [C.address, p.address],
    [C.phone, telLink(p.phone), true],
    [C.alone, p.alone ? C.aloneYes(p) : ""],
    [C.mobility, T.mobility[p.mobility] || p.mobility],
    [C.schedule, s ? `${T.schedule[s.kind] || T.schedule.days(s.days)}, ${T.schedule.window(s)}, ${T.channel[p.channel] || p.channel}` : ""],
    [C.worker, p.worker],
    [C.since, fmtDate(p.since)],
  ].filter(([, v]) => v);
  return `<dl class="kv kv--wide">${rows.map(([k, v, raw]) => `<dt>${k}</dt><dd>${raw ? v : esc(v)}</dd>`).join("")}</dl>`;
}

/** What the last call left for a person to do now (hooks.py decisions.emergency / crisis), while the senior is escalated
 *  for it: one line each and the SMS the operator sends with one click (action "notify", backend only). */
function alerts(p) {
  const d = store.get(p.id);
  if (stageOf(p) !== "escalated") return "";
  const since = stageDate(p) || "";
  const rows = [];
  const sms = (label, variant) => (variant ? `<div class="actions">${btn(label, `data-action="notify" data-id="${esc(p.id)}" data-channel="sms" data-variant="${esc(variant)}"`, "primary")}</div>` : "");
  const em = d.emergency;
  if (em && (em.date || "") >= since) {
    rows.push(`<li><b>${esc(C.emergency(C.emergencyKind[em.kind] || em.kind || "", fmtDate(em.date)))}</b>${sms(T.actions.notifyRelative, em.sms)}</li>`);
  }
  const cr = d.crisis;
  if (cr && (cr.date || "") >= since) {
    rows.push(`<li><b>${esc(C.crisis(fmtDate(cr.date)))}</b>${cr.lines ? `<br><span class="sn-muted">${esc(cr.lines)}</span>` : ""}${sms(T.actions.notifyCrisis, cr.sms)}</li>`);
  }
  if (!rows.length) return "";
  return `<section class="card__block"><h3>${C.alerts}</h3><ul class="warn">${rows.join("")}</ul></section>`;
}

/** A note a hook stored (decisions.health_note, decisions.schedule_note): a string, or {text|note|wish, date}. */
function noteText(n) {
  if (!n) return "";
  if (typeof n === "string") return n;
  if (typeof n !== "object") return String(n);
  const text = n.text || n.note || n.wish || n.complaint || n.value || "";
  const date = n.date || n.since || "";
  return [text, date ? fmtDate(date) : ""].filter(Boolean).join(", ");
}

function notes(p) {
  const d = store.get(p.id);
  const rows = [[C.healthNote, noteText(d.health_note)], [C.scheduleNote, noteText(d.schedule_note)],
    [C.humanRequest, d.human_request ? fmtDate(d.human_request.date) || C.humanRequestYes : ""]].filter(([, v]) => v);
  if (!rows.length) return "";
  return `<section class="card__block"><h3>${C.notes}</h3><dl class="sn-note">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl></section>`;
}

function mood(p) {
  const pts = moodSeries(p);
  const avg = pts.length ? (pts.reduce((s, x) => s + x.mood, 0) / pts.length).toFixed(1).replace(".", ",") : "";
  return `${moodChart(pts)}${avg ? `<p class="sn-muted">${C.moodAvg(avg)}, ${T.moodWord(pts.at(-1).mood)} ${fmtDate(pts.at(-1).date)}</p>` : ""}`;
}

const callLine = (p) => (c) => {
  const what = c.relative ? C.relativeSms : !c.answered ? (p.sex === "F" ? C.noAnswerF : C.noAnswer)
    : [T.intent[c.intent], (c.items || []).map(itemLabel).join(", ")].filter(Boolean).join(": ");
  const tag = c.via === "sim" ? C.simulated : c.live ? T.calls.live : "";
  return `<li><time>${fmtDate(c.date)}${c.time ? ` ${c.time}` : ""}</time><div>${c.answered ? `${moodBadge(c.mood)} ` : ""}${esc(what)}${tag ? ` <span class="sn-tag">${tag}</span>` : ""}
    ${c.text ? `<q>${esc(c.text)}</q>` : ""}${c.note ? `<span class="sn-muted">${esc(c.note)}</span>` : ""}${recapLine(c.summary, c.confirmed)}${dialogue(c.transcript)}</div></li>`;
};

function relative(p) {
  const r = p.relative;
  if (!r) return `<p class="sn-muted">${C.relativeNone}</p>`;
  const tel = (r.phone || "").replace(/\s/g, "");
  return `<div class="sn-rel"><dl class="kv"><dt>${esc(r.rel)}</dt><dd>${esc(r.name)}</dd>
    <dt>${C.phone}</dt><dd><a href="tel:${esc(tel)}">${esc(r.phone)}</a></dd></dl>
    ${tel ? `<a class="btn" href="tel:${esc(tel)}">${T.actions.callRelative}</a>` : ""}</div>`;
}

/** Simulated answer of the senior (demo), only on the card. Open when the presenter switched replies on in the demo panel. */
function simulated(p) {
  const stage = stageOf(p) || "new";
  const replies = cfg.REPLIES.filter((r) => allowed(stage, r)); // reply intents are journey events (dialog.INTENT_EVENT)
  if (!replies.length) return "";
  const on = !!document.querySelector('[data-action="toggle-replies"]:checked');
  return `<details class="sn-sim"${on ? " open" : ""}><summary>${T.demo.simTitle}</summary><p>${T.demo.simHint}</p>
    <div class="replies">${replies.map((r) => `<button type="button" data-action="sim-reply" data-reply="${r}" data-id="${esc(p.id)}">${esc(T.demo.replyOf(r, p))}</button>`).join("")}</div></details>`;
}

export function blocks(p) {
  const needs = openNeeds(p);
  const calls = callsOf(p);
  const li = callLine(p);
  return {
    before: `${alerts(p)}
      <section class="card__block"><h3>${C.relative}</h3>${relative(p)}</section>
      <section class="card__block"><h3>${C.needs}</h3>${needs.length ? chips(needs) : `<p class="sn-muted">${C.needsNone}</p>`}</section>
      <section class="card__block"><h3>${C.lastCalls}</h3>${calls.length ? `<ol class="sn-hist">${calls.slice(0, 3).map(li).join("")}</ol>` : `<p class="sn-muted">${T.detail.noContacts}</p>`}</section>
      <section class="card__block"><h3>${C.facts}</h3>${facts(p)}</section>
      ${notes(p)}`,
    after: `<details class="card__more"><summary>${C.moreTitle}</summary>
        <h3>${C.moodChart}</h3>${mood(p)}
        <h3>${C.allCalls(calls.length)}</h3>${calls.length ? `<ol class="sn-hist">${calls.map(li).join("")}</ol>` : `<p class="sn-muted">${T.detail.noContacts}</p>`}
        <p class="sn-muted">${esc(p.id)}, ${esc(p.district)}</p></details>
      ${simulated(p)}`,
  };
}
