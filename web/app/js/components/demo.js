// Presenter controls, kept apart from the product: simulated replies and (with the backend) the demo clock.
import { T } from "../i18n/cs.js";
import { esc, fmtDate } from "../util.js";

function recipientForm(r, error) {
  const D = T.demo.to;
  return `<div class="demo__to">
      <b>${D.title}</b>
      <label class="field"><span>${D.phone}</span><input id="rcp-phone" type="tel" inputmode="tel" autocomplete="tel"
        value="${r.customPhone ? esc(r.phone) : ""}" placeholder="${r.customPhone ? "" : esc(r.phone)}"></label>
      <label class="field"><span>${D.email}</span><input id="rcp-email" type="email" autocomplete="email"
        value="${r.customEmail ? esc(r.email) : ""}" placeholder="${r.customEmail ? "" : esc(r.email)}"></label>
      ${error ? `<p class="demo__err" role="alert">${esc(error)}</p>` : ""}
      <p class="demo__hint">${D.hint(r)}</p>
      <div class="demo__row"><button type="button" class="btn" data-action="recipient-save">${D.save}</button>
        ${!r.session && (r.customPhone || r.customEmail) ? `<button type="button" class="btn btn--link" data-action="recipient-reset">${D.reset}</button>` : ""}
        ${r.session ? `<a class="btn btn--link" href="/logout">${D.logout}</a>` : ""}</div>
    </div>`;
}

export function demoPanel({ replies, clock, fhir, recipient, recipientError }) {
  return `<summary>${T.demo.title}</summary>
    <div class="demo__body">
      <p>${T.demo.intro}</p>
      ${recipient ? `<a class="btn" href="/sal" target="_blank" rel="noopener">${T.demo.hall}</a>` : ""}
      ${recipient ? recipientForm(recipient, recipientError) : ""}
      ${clock ? `<div><b>${T.demo.clock(fmtDate(clock))}</b></div>
        <button type="button" class="btn" data-action="tick">${T.demo.next}</button>` : ""}
      <label><input type="checkbox" data-action="toggle-replies" ${replies ? "checked" : ""}> ${T.demo.replies}</label>
      ${fhir ? `<button type="button" class="btn" data-action="fhir-sync">${T.demo.fhirSync}</button>` : ""}
      <button type="button" class="btn btn--link" data-action="reset">${T.demo.reset}</button>
    </div>`;
}
