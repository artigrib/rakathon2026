import { CHANNELS } from "../config.js";
import { T } from "../i18n/cs.js";
import { fixedText, message } from "../content/messages.cs.js";
import { cap, esc, html } from "../util.js";
import { failedChannels, plannedContact } from "../domain.js";

export function compose(p, chosenChannel) {
  const plan = plannedContact(p);
  const channel = chosenChannel || plan.channel;
  const failed = failedChannels(p);
  return html`<div class="compose" data-compose="${p.id}">
    <span class="compose__label" id="chl-${p.id}">${T.compose.channel}</span>
    <div class="channels" role="group" aria-labelledby="chl-${p.id}">
      ${CHANNELS.map((c) => {
        const disabled = c === "portal" && !p.portal;
        const note = c === plan.channel ? T.channelRecommended : failed.has(c) ? T.channelFailed : "";
        return `<button type="button" data-action="pick-channel" data-id="${p.id}" data-channel="${c}"
          aria-pressed="${c === channel}" ${disabled ? `disabled title="${esc(T.channelNoPortal)}"` : ""}>
          ${cap(T.channel[c])}${note ? `<small>${note}</small>` : ""}</button>`;
      })}
    </div>
    <label class="compose__label" for="msg-${p.id}">${channel === "voice" ? T.compose.voiceText : T.compose.text}</label>
    <textarea id="msg-${p.id}" ${fixedText(channel) ? "readonly" : ""}>${esc(message(p, channel, plan.variant))}</textarea>
    <div class="compose__foot">
      <p>${fixedText(channel) ? T.compose.trial : T.compose.note}</p>
      <button type="button" class="btn" data-action="close-compose">${T.actions.cancel}</button>
      <button type="button" class="btn btn--primary" data-action="confirm-send" data-id="${p.id}" data-channel="${channel}">${T.actions.confirmSend(T.channel[channel])}</button>
    </div>
  </div>`;
}
