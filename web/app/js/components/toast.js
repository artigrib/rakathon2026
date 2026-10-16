import { T } from "../i18n/cs.js";
import { store } from "../state.js";

let timer;
export function toast(text, { undo = true } = {}) {
  const el = document.getElementById("toast");
  el.innerHTML = `<span>${text}</span>${undo && store.canUndo() ? `<button type="button" data-action="undo">${T.actions.undo}</button>` : ""}`;
  el.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => (el.hidden = true), 6000);
}
export function hideToast() { document.getElementById("toast").hidden = true; }
