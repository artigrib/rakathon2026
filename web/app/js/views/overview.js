import { T } from "../i18n/cs.js";
import { fmtDate, html, countBy } from "../util.js";
import { bucketOf, practices, stageOf } from "../domain.js";
import { store } from "../state.js";

const O = T.overview;

export function overview(data) {
  const P = data.patients;
  const byStatus = countBy(P, (p) => p.status);
  const contacted = P.filter((p) => store.get(p.id).sent || p.history.some((h) => h.type === "lung_screening_information")).length;
  const reached = (stages) => P.filter((p) => (store.get(p.id).journey || []).some((e) => stages.includes(e.stage)) || stages.includes(stageOf(p))).length;
  const steps = [P.length, byStatus.ELIGIBLE || 0, byStatus.NEEDS_REVIEW || 0, contacted,
    reached(["interested", "callback", "booked"]), reached(["booked"]), reached(["result"])];

  const funnel = steps.map((v, i) => html`<div class="funnel__row">
    <div class="funnel__bar"><i style="width:${Math.max(1, (v / P.length) * 100)}%"></i><span>${O.funnelSteps[i]}</span></div>
    <b>${v}</b></div>`);

  const reasons = O.exclusionRows.map(([code, label]) => `<div><dt>${label}</dt><dd>${byStatus[code] || 0}</dd></div>`);

  const rows = practices(P).map((gp) => {
    const m = P.filter((p) => p.gp === gp);
    const b = countBy(m, bucketOf);
    return { gp, n: m.length, e: m.filter((p) => p.status === "ELIGIBLE").length, c: b.contact || 0, i: b.interested || 0, r: b.review || 0 };
  }).sort((a, b) => b.c - a.c);

  const issues = data.issues;
  const missing = issues.filter((i) => i.code === "MISSING_COLUMN").length;
  const enc = issues.find((i) => i.code === "ENCODING_REPAIRED");
  const encN = enc ? +(enc.text.match(/\d+/) || [0])[0] : 0;
  const flagged = (codes) => P.filter((p) => p.flags.some((f) => codes.includes(f.code))).length;

  return html`
    <section class="pagehead"><h1>${O.title}</h1><p>${O.lede(P.length, practices(P).length, fmtDate(data.refDate))}</p></section>
    <div class="grid2">
      <section class="panel"><h2>${O.funnel}</h2><div class="funnel">${funnel}</div></section>
      <section class="panel"><h2>${O.exclusions}</h2><dl class="reasons">${reasons}</dl></section>
    </div>
    <section class="panel">
      <h2>${O.practices}</h2><p class="pt__why" style="margin:0">${O.practicesHint}</p>
      <div class="tablewrap"><table>
        <thead><tr>${O.cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => `<tr tabindex="0" data-action="open-practice" data-gp="${r.gp}"><td class="mono">${r.gp}</td><td class="n">${r.n}</td><td class="n">${r.e}</td><td class="n">${r.c}</td><td class="n">${r.i}</td><td class="n">${r.r}</td></tr>`)}</tbody>
      </table></div>
    </section>
    <section class="panel"><h2>${O.dataQuality}</h2><ul class="dq">
      ${missing ? `<li>${O.dq.rows(missing)}</li>` : ""}
      ${encN ? `<li>${O.dq.encoding(encN)}</li>` : ""}
      <li>${O.dq.conflict(flagged(["PY_CONFLICT"]))}</li>
      <li>${O.dq.ct(flagged(["CT_SCHEDULED", "CT_CANCELLED"]))}</li>
    </ul></section>`;
}
