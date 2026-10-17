import { T } from "../i18n/cs.js";
import { fmtDate, countBy } from "../util.js";
import { batchOf, practices, stageOf, taskOf } from "../domain.js";
import { store } from "../state.js";

const O = T.overview;

const section = (id, title, body) => `<section class="section grid" aria-labelledby="o-${id}">
  <div class="section__aside"><h2 id="o-${id}">${title}</h2></div>
  <div class="section__body">${body}</div></section>`;

export function overview(data) {
  const P = data.patients;
  const byStatus = countBy(P, (p) => p.status);
  const contacted = P.filter((p) => store.get(p.id).sent || p.history.some((h) => h.type === "lung_screening_information")).length;
  const reached = (stages) => P.filter((p) => (store.get(p.id).journey || []).some((e) => stages.includes(e.stage)) || stages.includes(stageOf(p))).length;
  const steps = [P.length, byStatus.ELIGIBLE || 0, byStatus.NEEDS_REVIEW || 0, contacted,
    reached(["interested", "callback", "booked"]), reached(["booked"]), reached(["result"])];
  const funnel = `<ol class="stats">${steps.map((v, i) => `<li class="${i >= 4 ? "is-key" : ""}"><div>${O.funnelSteps[i]}
    <div class="bar"><i style="width:${Math.max(0.5, (v / P.length) * 100)}%"></i></div></div><b>${v}</b></li>`).join("")}</ol>`;

  // Programme results so far (SPEC.md): 18 % of the target population reached, 54.4 % of those referred (01196).
  const E = byStatus.ELIGIBLE || 0;
  const today = [Math.round(E * 0.18), Math.round(E * 0.18 * 0.544)];
  const ours = [E, Math.round(E * 0.544)];
  const impact = `<div class="tablewrap"><table class="impact">
    <thead><tr>${O.impactCols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead>
    <tbody>${O.impactRows.map((r, i) => `<tr><td>${r}</td><td class="n">${today[i]}</td><td class="n"><b>${ours[i]}</b></td></tr>`).join("")}</tbody>
  </table></div><p class="note">${O.impactNote(E)}</p>`;

  // Which channel works (mentor: the doctor wants to know whether it had an effect). A reply counts for the
  // channel of the last contact before it; records from the practice data count too.
  const ch = {};
  const add = (c, k) => { if (!c) return; ch[c] ||= { sent: 0, replied: 0 }; ch[c][k]++; };
  for (const p of P) {
    for (const h of p.history) { add(h.channel, "sent"); if (h.response === "interested") add(h.channel, "replied"); }
    let last = null;
    for (const e of store.get(p.id).journey || []) {
      if (e.stage === "sent") { add(e.channel, "sent"); last = e.channel; }
      else if (e.text && last && !e.ignored) { if (["interested", "booked", "callback"].includes(e.intent)) add(last, "replied"); last = null; }
    }
  }
  const chRows = Object.entries(ch).sort((a, b) => b[1].replied / b[1].sent - a[1].replied / a[1].sent);
  const channels = chRows.length ? `<div class="tablewrap"><table>
    <thead><tr>${O.chCols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead>
    <tbody>${chRows.map(([c, v]) => `<tr><td>${T.channel[c] || c}</td><td class="n">${v.sent}</td><td class="n">${v.replied}</td><td class="n"><b>${Math.round((100 * v.replied) / v.sent)} %</b></td></tr>`).join("")}</tbody>
  </table></div><p class="note">${O.chNote}</p>` : "";

  const reasons = `<ul class="stats">${O.exclusionRows.map(([code, label]) => `<li><div>${label}</div><b>${byStatus[code] || 0}</b></li>`).join("")}</ul>`;

  const rows = practices(P).map((gp) => {
    const m = P.filter((p) => p.gp === gp);
    const t = countBy(m, (p) => taskOf(p) || "-");
    return { gp, n: m.length, e: m.filter((p) => p.status === "ELIGIBLE").length, c: batchOf(m).length, i: t.replied || 0, r: t.doctor || 0 };
  }).sort((a, b) => b.c + b.i + b.r - (a.c + a.i + a.r));
  const table = `<div class="tablewrap"><table>
    <thead><tr>${O.cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${c}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr tabindex="0" data-action="open-practice" data-gp="${r.gp}"><td>${r.gp}</td><td class="n">${r.n}</td><td class="n">${r.e}</td><td class="n">${r.c}</td><td class="n">${r.i}</td><td class="n">${r.r}</td></tr>`).join("")}</tbody>
  </table></div>`;

  const issues = data.issues;
  const missing = issues.filter((i) => i.code === "MISSING_COLUMN").length;
  const enc = issues.find((i) => i.code === "ENCODING_REPAIRED");
  const encN = enc ? +(enc.text.match(/\d+/) || [0])[0] : 0;
  const flagged = (codes) => P.filter((p) => p.flags.some((f) => codes.includes(f.code))).length;
  const dq = `<ul class="dq">${missing ? `<li>${O.dq.rows(missing)}</li>` : ""}${encN ? `<li>${O.dq.encoding(encN)}</li>` : ""}
    <li>${O.dq.conflict(flagged(["PY_CONFLICT"]))}</li><li>${O.dq.ct(flagged(["CT_SCHEDULED", "CT_CANCELLED"]))}</li></ul>`;

  return `<header class="pagehead"><h1>${O.title}</h1><p>${O.sub(P.length, practices(P).length, fmtDate(data.refDate))}</p></header>
    ${section("impact", O.impact, impact)}
    ${section("funnel", O.funnel, funnel)}
    ${channels ? section("channels", O.channels, channels) : ""}
    ${section("why", O.exclusions, reasons)}
    ${section("practices", O.practices, table)}
    ${section("dq", O.dataQuality, dq)}`;
}
