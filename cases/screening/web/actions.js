// Screening click actions on top of the core ones (core/shell.js): the doctor includes / excludes a patient,
// acknowledges a result. app = {ui, data, store, T, toast, send, mark, step, find, today, backend}.
export const actions = {
  include: async (el, app) => {
    const id = el.dataset.id;
    if (app.store.get(id).override === "EXCLUDED" || app.store.get(id).stage === "excluded") await app.step(id, { stage: "include" });
    await app.mark(id, "override", "ELIGIBLE"); app.toast(el.dataset.exception ? app.T.toast.exception : app.T.toast.included, { undo: !app.backend });
  },
  exclude: async (el, app) => {
    await app.step(el.dataset.id, { stage: "exclude" }); await app.mark(el.dataset.id, "override", "EXCLUDED");
    app.toast(app.T.toast.excluded, { undo: !app.backend });
  },
  ack: async (el, app) => { await app.mark(el.dataset.id, "resultAck", true); app.toast(app.T.toast.ack, { undo: !app.backend }); },
};
