// Patient-facing messages. Texts live in content/messages.cs.json (shared with the backend, which sends
// automatic follow-ups with exactly the same wording). This module only fills placeholders.
import { MESSAGES_URL, PRACTICES } from "../config.js";

let M = null;
let withLink = false; // in live mode the backend replaces the marker with the patient's personal link
let trial = false; // Twilio trial: a live SMS must fit one segment, the backend sends sms.TRIAL instead

export async function loadMessages(opts = {}) {
  M = await (await fetch(MESSAGES_URL)).json();
  withLink = !!opts.withLink;
  trial = !!opts.trial;
}

/** In live mode the server appends the patient's personal reply link to SMS, WhatsApp and e-mail. */
export const linkNote = (channel) => withLink && ["sms", "whatsapp", "email"].includes(channel) && !trial;

/** True when this channel sends the fixed short trial text (the nurse cannot edit it). */
export const fixedText = (channel) => trial && channel === "sms";

const gsm = (s) => s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

const fill = (tpl, vars) => tpl.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));

export function message(patient, channel, variant = "FIRST_INVITE") {
  if (fixedText(channel)) return gsm(M.sms.TRIAL); // exactly what the backend sends
  const set = M[M.channel_template[channel] || "email"];
  const phone = PRACTICES[patient.gp]?.phone;
  const url = ""; // the personal link is added by the server when sending (see linkNote)
  return fill(set[variant] || set.FIRST_INVITE, {
    gp: patient.gp,
    contact: patient.pneu ? M.parts.contact_with_pneu : M.parts.contact,
    call_us: phone ? fill(M.parts.call_us, { phone }) : "",
    link: url ? fill(M.parts.link, { url }) : "",
    link_short: url ? fill(M.parts.link_short, { url }) : "",
  });
}
