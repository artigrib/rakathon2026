// One debtor = one row: what is going on (one sentence) and what the operator can do (only what the journey allows).
import { T, money } from "./i18n.js";
import { cap, fmtDate } from "core/util.js";
import { OFFER_DAYS } from "./config.js";
import { addDays, automated, canContact, lastEvent, openPromise, plannedContact, remaining, stageOf, strategyOf, segmentOf } from "./domain.js";
import { btn, stepBtn } from "core/components/row.js";

const S = T.state;
const A = T.actions;
let current = null;
const step = (id, ev, label, kind = "", extra = "") => stepBtn(current, id, ev, label, kind, extra);
const via = (e) => S.via[e?.via] || "";

export const rowClass = (p, d) => (d.skipped && !stageOf(p) ? " row--skipped" : "");

function handoffWhy(p, d) {
  const e = lastEvent(p, "human_handoff");
  if (!e) return S.handoff.default;
  if (e.extra?.reason === "verification_failed") return S.handoff.verification;
  if (e.event === "human" && e.auto) return S.handoff.human;
  return S.handoff[e.intent] || S.handoff[e.event] || S.handoff.default;
}

/** {title, sub} in plain words. */
export function describe(p, d, plan) {
  const stage = stageOf(p);
  const nextLine = plan ? (plan.channel === "human" ? S.nextHuman(fmtDate(plan.due)) : S.next(fmtDate(plan.due), plan.at || "9:00", T.channel[plan.channel])) : "";
  switch (stage) {
    case null: {
      const facts = `${money(p.outstanding)}, ${T.product[p.product].toLowerCase()} · ${p.reason}`;
      if (!automated(p)) return { title: S.readyHuman(T.segment[segmentOf(p)]), sub: facts };
      if (d.skipped) return { title: S.skipped, sub: facts };
      return { title: cap(S.ready(T.strategyShort[strategyOf(p)], T.channel[plannedContact(p).channel])), sub: d.draft ? S.edited : facts };
    }
    case "contacted": {
      const del = [...(d.journey || [])].reverse().find((e) => e.delivery)?.delivery;
      return { title: S.contacted(fmtDate(d.sent?.date), T.channel[d.sent?.channel] || "") + (del ? `, ${T.detail.delivery[del] || del}` : ""), sub: nextLine || S.planEnd };
    }
    case "promise_to_pay": {
      const pr = openPromise(d);
      return pr ? { title: S.promise(money(pr.amount), fmtDate(pr.date)), sub: S.promiseSub(fmtDate(pr.made), S.via[pr.via] || "") } : { title: S.promise("", "") };
    }
    case "broken_promise": {
      const br = [...(d.promises || [])].reverse().find((x) => x.status === "broken");
      return { title: S.broken(br ? fmtDate(br.date) : ""), sub: plan ? S.brokenSub(fmtDate(plan.due), T.channel[plan.channel]) : "" };
    }
    case "plan_offered": {
      const e = lastEvent(p, "plan_offered");
      const paid = (d.payments || []).reduce((a, x) => a + (+x.amount || 0), 0);
      return { title: e?.event === "partial_paid" ? S.partial(money(paid), money(remaining(p, d))) : S.planOffered, sub: S.planOfferedSub(fmtDate(addDays(e?.date || "", OFFER_DAYS))) };
    }
    case "plan_active": {
      const pl = d.plan || { items: [] };
      const next = pl.items.find((i) => i.status === "open");
      if (pl.kind === "deferral") return { title: S.deferral(fmtDate(pl.items[0]?.due)), sub: next ? S.planNext(fmtDate(next.due), money(next.amount)) : "" };
      return { title: S.planActive(pl.items.filter((i) => i.status === "paid").length, pl.n || pl.items.length, money(pl.monthly)), sub: next ? S.planNext(fmtDate(next.due), money(next.amount)) : "" };
    }
    case "refi_offered": return { title: S.refiOffered, sub: S.refiOfferedSub(fmtDate(addDays(lastEvent(p, "refi_offered")?.date || "", OFFER_DAYS))) };
    case "refi_accepted": return { title: S.refiAccepted, sub: S.refiAcceptedSub };
    case "human_handoff": {
      const e = lastEvent(p, "human_handoff");
      return { title: handoffWhy(p, d) + (e?.when ? `, ${e.when}` : ""), sub: e?.text ? `„${e.text}“` : S.replied(fmtDate(e?.date), via(e)) };
    }
    case "dispute": return { title: S.dispute, sub: lastEvent(p, "dispute")?.text ? `„${lastEvent(p, "dispute").text}“` : p.dispute?.note || "" };
    case "hardship_review": return { title: S.hardship, sub: lastEvent(p, "hardship_review")?.text ? `„${lastEvent(p, "hardship_review").text}“` : p.vulnerable?.note || "" };
    case "wrong_contact": return { title: S.wrong, sub: S.replied(fmtDate(lastEvent(p, "wrong_contact")?.date), via(lastEvent(p, "wrong_contact"))) };
    case "paid": return { title: S.paid(money(Math.max(p.outstanding, (d.payments || []).reduce((a, x) => a + (+x.amount || 0), 0)))), sub: S.replied(fmtDate(lastEvent(p, "paid")?.date), via(lastEvent(p, "paid"))) };
    case "do_not_contact": return { title: S.dnc, sub: S.replied(fmtDate(lastEvent(p, "do_not_contact")?.date), via(lastEvent(p, "do_not_contact"))) };
    case "closed": return { title: S.closed };
  }
  return { title: stage };
}

export function actions(p, d) {
  const id = p.id;
  const stage = stageOf(p);
  current = stage;
  switch (stage) {
    case null:
      if (!automated(p)) {
        if (segmentOf(p) === "dispute") return step(id, "dispute", A.takeDispute, "primary");
        if (segmentOf(p) === "vulnerable") return step(id, "vulnerable", A.takeHardship, "primary");
        return step(id, "human", A.take, "primary");
      }
      if (d.skipped) return btn(A.unskip, `data-action="unskip" data-id="${id}"`, "link");
      return (canContact(p) ? btn(A.contact, `data-action="open-compose" data-id="${id}"`) : `<span class="muted">${A.notToday}</span>`)
        + btn(A.skip, `data-action="skip" data-id="${id}"`, "link");
    case "contacted":
    case "broken_promise":
      return step(id, "paid", A.paid, "link") + step(id, "human", A.take, "link");
    case "promise_to_pay":
      return step(id, "paid", A.paid, "primary") + step(id, "broken", A.broken, "link");
    case "plan_offered":
    case "refi_offered":
      return step(id, "paid", A.paid, "link") + step(id, "human", A.take, "link");
    case "plan_active":
      return step(id, "paid", A.paid, "link") + step(id, "plan_missed", A.missed, "link");
    case "refi_accepted":
      return step(id, "paid", A.refiDone, "primary") + step(id, "human", A.take, "link");
    case "human_handoff":
      return (strategyOf(p) === "refi" ? step(id, "want_refi", A.offerRefi) : step(id, "need_plan", A.offerPlan))
        + step(id, "resume", A.resume, "link") + step(id, "close", A.close, "link");
    case "dispute":
      return step(id, "resume", A.resume) + step(id, "close", A.close, "link");
    case "hardship_review":
      return step(id, "need_plan", A.offerPlan) + step(id, "resume", A.resume, "link") + step(id, "close", A.close, "link");
    case "wrong_contact":
      return step(id, "contact_fixed", A.fixed) + step(id, "close", A.close, "link");
  }
  return "";
}
