// AI vymáhání: product decisions, not code. Thresholds of the segmentation live in ../strategy.py,
// the contact limits in ../cadence.py (mirrored here only for display and the operator's send button).

export const CHANNELS = ["sms", "voice", "email", "whatsapp"];
export const FILTERS = ["all", "lost", "operator", "supervisor", "system", "done"];
// Simulated replies in the demo (journey events = dialog intents); with the backend the text goes through the real
// reply understanding (rules / AI) and hooks.on_reply records the promise, the plan or the stop.
export const REPLIES = ["will_pay", "need_plan", "want_refi", "dispute", "vulnerable", "wrong_person", "channel_opt_out", "opt_out"];
export const JOURNEY = [
  { key: "contacted", stages: ["contacted", "broken_promise"] },
  { key: "answered", stages: ["plan_offered", "refi_offered", "human_handoff", "hardship_review", "dispute"] },
  { key: "agreed", stages: ["promise_to_pay", "plan_active", "refi_accepted"] },
  { key: "paid", stages: ["paid"] },
];
// Queue sections in order (Fronta). Automated strategies first (one approval sends the batch), then people.
export const QUEUE = ["reminder", "plan", "refi", "operator", "supervisor", "human"];
export const AUTOMATED = ["reminder", "plan", "refi"];
export const SEGMENTS = ["forgetful", "temporary", "long_term", "uncooperative", "dispute", "vulnerable"];
export const STRATEGY = { forgetful: "reminder", temporary: "plan", long_term: "refi", uncooperative: "supervisor", dispute: "human", vulnerable: "human" };
export const PORTFOLIOS = ["Spotřebitelské úvěry", "Kreditní karty", "BNPL", "Telefony na splátky"];

// Same as cadence.py.
export const WEEKLY_CAP = 3;
export const CONTACT_HOURS = [8, 20];
export const FIXED_HOLIDAYS = ["01-01", "05-01", "05-08", "07-05", "07-06", "09-28", "10-28", "11-17", "12-24", "12-25", "12-26"];
export const EASTER = { 2025: "04-20", 2026: "04-05", 2027: "03-28", 2028: "04-16" };

// Days a handed-over client may wait for a person before the row says "getting lost".
export const LOST_DAYS = 3;
export const OFFER_DAYS = 7;
export const PLAN_MONTHS = [3, 6, 12];
export const PLAN_MIN_INSTALMENT = 500;
export const REFI_RATE = 0.099;
export const REFI_TERMS = [24, 36, 48, 60];
