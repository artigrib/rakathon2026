// Click actions of Jsem v pořádku on top of the core ones (core/shell.js).
// app = {ui, data, store, T, toast, send, mark, step, find, today, backend}.
import { mineOf } from "core/case.js";
import { entries } from "./views/basket.js";
import { itemLabel } from "./domain.js";

const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

export const actions = {
  // Basket status of one need: new → ordered (objednáno) → done (vyřízeno). Stored as the mark "basket" (case.json marks).
  "basket-status": async (el, app) => {
    const { id, need, status } = el.dataset;
    await app.mark(id, "basket", { ...(app.store.get(id).basket || {}), [need]: status });
    app.toast(app.T.toast.basket[status], { undo: !app.backend });
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
