// Patient-facing messages. Texts live in content/messages.cs.json (shared with the backend, which sends
// automatic follow-ups with exactly the same wording). This module only fills placeholders.
import { MESSAGES_URL, PRACTICES } from "../config.js";

let M = null;
let withLink = false; // in live mode the backend replaces the marker with the patient's personal link

export async function loadMessages(opts = {}) {
  M = await (await fetch(MESSAGES_URL)).json();
  withLink = !!opts.withLink;
}

const fill = (tpl, vars) => tpl.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));

export function message(patient, channel, variant = "FIRST_INVITE") {
  const set = M[M.channel_template[channel] || "email"];
  const phone = PRACTICES[patient.gp]?.phone;
  const url = withLink ? M.parts.link_marker : "";
  return fill(set[variant] || set.FIRST_INVITE, {
    gp: patient.gp,
    contact: patient.pneu ? M.parts.contact_with_pneu : M.parts.contact,
    call_us: phone ? fill(M.parts.call_us, { phone }) : "",
    link: url ? fill(M.parts.link, { url }) : "",
    link_short: url ? fill(M.parts.link_short, { url }) : "",
  });
}
