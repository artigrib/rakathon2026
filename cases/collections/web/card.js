// Debtor card blocks: the obligation, segment and strategy with the rule that chose it, contact limits and consents,
// promises, plan and refinancing before the journey; contacts after the communication timeline.
import { T, money } from "./i18n.js";
import { esc, fmtDate } from "core/util.js";
import { blockedChannels, contactsInWeek, clock, paidTotal, refiExample, remaining, segmentOf, strategyOf, weeklyCap, automated } from "./domain.js";
import { store } from "core/state.js";

const C = T.card;
const kv = (rows) => `<dl class="kv kv--wide">${rows.filter(Boolean).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
const block = (title, body) => `<section class="card__block"><h3>${title}</h3>${body}</section>`;
const ST = T.promisesView.status;

function debt(p, d) {
  const paid = paidTotal(d);
  return kv([
    [C.product, esc(T.product[p.product] || p.product)],
    [C.contract, esc(p.contract)],
    [C.outstanding, `<b>${money(p.outstanding)}</b>`],
    paid ? [C.paid, money(paid)] : null,
    paid || d.stage === "paid" ? [C.remaining, money(remaining(p, d))] : null,
    [C.dpd, `${p.dpd}`],
    [C.dueSince, fmtDate(p.dueSince)],
    [C.instalment, money(p.instalment)],
    [p.product === "card" ? C.principal : C.principal, money(p.principal)],
    [C.balance, money(p.balance)],
  ]);
}

function strategyBlock(p) {
  const seg = segmentOf(p);
  const s = strategyOf(p);
  const kept = (p.promises || []).filter((x) => x.kept).length;
  return `<p><b>${T.segment[seg]}</b> → ${T.strategy[s]}</p>
    <p class="muted">${esc(p.reason)} (${C.rule(p.rule)}). ${automated(p) ? C.auto : C.noAuto}.</p>
    ${kv([[C.income, T.income[p.income] || p.income], [C.otherLoans, String(p.otherLoans || 0)], [C.history, C.historyLine(kept, (p.promises || []).length)]])}`;
}

function compliance(p, d) {
  const b = blockedChannels(d);
  const day = clock();
  return kv([
    [C.window, C.week(contactsInWeek(d, day), weeklyCap)],
    [C.blocked, b === "all" ? C.all : b.length ? b.map((c) => T.channel[c]).join(", ") : C.none],
    [C.verified, d.verifyLocked ? C.locked : d.verified ? C.verifiedOn(fmtDate(d.verified)) : C.notVerified],
    d.contactInvalid ? [C.invalid, fmtDate(d.contactInvalid.date)] : null,
  ]);
}

function promises(p, d) {
  const rows = [
    ...(d.promises || []).map((x) => `<li><time>${fmtDate(x.made)}</time><span>${money(x.amount)} do ${fmtDate(x.date)}${x.dateGiven === false ? ` (${T.promisesView.noDate})` : ""}: <b>${ST[x.status] || x.status}</b>${x.via ? `, ${esc(T.state.via[x.via] || x.via)}` : ""}</span></li>`).reverse(),
    ...(p.promises || []).map((x) => `<li><time>${fmtDate(x.date)}</time><span>${money(x.amount)}: ${x.kept ? ST.kept : ST.broken} <span class="muted">(${C.fromHistory})</span></span></li>`).reverse(),
  ];
  return rows.length ? `<ul class="timeline">${rows.join("")}</ul>` : "";
}

function plan(d) {
  const pl = d.plan;
  if (!pl?.items?.length) return "";
  return `<ul class="timeline">${pl.items.map((i, k) => `<li><time>${fmtDate(i.due)}</time><span>${k + 1}. ${money(i.amount)}: <b>${ST[i.status] || i.status}</b></span></li>`).join("")}</ul>`;
}

function refi(p, d) {
  if (!d.refi && strategyOf(p) !== "refi") return "";
  const e = d.refi?.example || refiExample(remaining(p, d) || p.outstanding);
  return `<p>${money(e.principal)}: ${C.refiLine(e)}</p><p class="muted">${C.refiNote}</p>`;
}

function contacts(p) {
  return kv([
    [C.phone, `${esc(p.phone)} <span class="muted">(${C.fake})</span>`],
    [C.email, esc(p.email)],
    [C.prefers, esc(T.channel[p.pref] || p.pref)],
    [C.city, esc(p.city)],
    [C.age, `${p.age}`],
  ]) + `<p class="muted">${p.id}, ${esc(p.portfolio)}</p>`;
}

export function blocks(p) {
  const d = store.get(p.id);
  const pr = promises(p, d);
  const pl = plan(d);
  const rf = refi(p, d);
  return {
    before: block(C.debt, debt(p, d)) + block(C.strategy, strategyBlock(p)) + block(C.compliance, compliance(p, d))
      + (pr ? block(C.promises, pr) : "") + (pl ? block(C.plan, pl) : "") + (rf ? block(C.refi, rf) : ""),
    after: block(C.contacts, contacts(p)),
  };
}
