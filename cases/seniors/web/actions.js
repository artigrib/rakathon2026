// Click actions of Jsem v pořádku on top of the core ones (core/shell.js).
// app = {ui, data, store, T, toast, send, mark, step, find, today, backend}.
import { mineOf } from "core/case.js";
import { entries } from "./views/basket.js";
import { itemLabel, openNeeds, stageOf } from "./domain.js";

const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

/** Basket statuses of every open need of the senior set to `status` (the mark "basket"). */
async function closeNeeds(app, id, status = "done") {
  const p = app.find(id);
  const open = p ? openNeeds(p) : [];
  if (!open.length) return 0;
  const basket = { ...(app.store.get(id).basket || {}) };
  for (const n of open) basket[n.id] = status;
  await app.mark(id, "basket", basket);
  return open.length;
}

export const actions = {
  // Basket status of one need: new → ordered (objednáno) → done (vyřízeno). Stored as the mark "basket" (case.json marks).
  // When the last open need of a senior waiting for help is done, the senior's row is resolved too (one truth).
  "basket-status": async (el, app) => {
    const { id, need, status } = el.dataset;
    await app.mark(id, "basket", { ...(app.store.get(id).basket || {}), [need]: status });
    const p = app.find(id);
    if (status === "done" && p && stageOf(p) === "needs_help" && !openNeeds(p).length) {
      await app.step(id, { stage: "resolve" });
      app.toast(app.T.toast.needsDone, { undo: false });
      return;
    }
    app.toast(app.T.toast.basket[status], { undo: !app.backend });
  },
  // "Vyřešeno" on a row or the card: the journey event and the senior's open needs in the basket closed together.
  resolve: async (el, app) => {
    const { id } = el.dataset;
    await app.step(id, { stage: "resolve" });
    await closeNeeds(app, id);
    app.toast(app.T.toast.step.resolve, { undo: !app.backend });
  },
  // Simulated answer of a senior from the card (demo): the sentence agrees with the senior's gender and goes through
  // the real reply understanding, like the core "reply" action.
  "sim-reply": async (el, app) => {
    const { id, reply } = el.dataset;
    const p = app.find(id);
    await app.step(id, { reply, text: app.T.demo.replyTextOf(reply, p) });
    app.toast(app.T.toast.reply(app.T.demo.replyOf(reply, p)), { undo: !app.backend });
  },
  "basket-filter": (el, app) => { app.ui.basketFilter = el.dataset.filter; },
  "calls-filter": (el, app) => { app.ui.callsFilter = el.dataset.filter; },
  "calls-range": (el, app) => { app.ui.callsRange = +el.dataset.range; },
  "pick-district": (el, app) => { app.ui.gp = el.dataset.gp; window.scrollTo(0, 0); },
  // The whole basket of the district (every status), semicolon separated with a BOM, so Excel in Czech opens it as is.
  "basket-csv": (el, app) => {
    const L = app.T.basket;
    const rows = entries(mineOf(app.data, app.ui)).map((n) => [n.p.district, n.p.worker, n.p.name, n.p.address, n.p.phone,
      itemLabel(n.item), n.date, L.status[n.status]]);
    const csv = "﻿" + [L.csvCols, ...rows].map((r) => r.map(csvCell).join(";")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `kosik-${(app.ui.gp || "vse").replace(/\W+/g, "-")}-${app.today()}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    app.toast(app.T.toast.csv(rows.length), { undo: false });
  },
};
