// Jsem v pořádku configuration: product decisions, not code. (Data file, storage key, default district: ../case.json.)

// Compose buttons on a row (the check-in goes by the assistant's call; SMS for seniors who do not hear well). No e-mail: seniors
// have a phone, the relative gets an SMS.
export const CHANNELS = ["voice", "sms"];

// Simulated answers of a senior (demo): T.demo.reply[r], T.demo.replyText[r] (sent through the real reply understanding).
export const REPLIES = ["ok", "need_items", "low_mood", "health_problem", "emergency", "callback"];

// Journey on the senior's card.
export const JOURNEY = [
  { key: "called", stages: ["no_answer", "enrolled"] },
  { key: "answered", stages: ["ok", "needs_help", "low_mood", "callback"] },
  { key: "escalated", stages: ["escalated"] },
  { key: "resolved", stages: ["resolved"] },
];

// Kartotéka seniorů tabs: owner keys (domain.ownerOf) + "all". "paused" = stage paused or declined (owner paused | done,
// "Neaktivní"); "lost" shows under operator; "system" only in "all".
export const FILTERS = ["all", "social", "operator", "paused"];

// Phone of the social service per district for {call_us} (empty = omitted from texts).
export const PRACTICES = {};

// Stages that get no scheduled check-in call (a person decides first, or the senior said no). low_mood stays open
// until the operator or the social worker decides; a batch call must not overwrite the alert.
export const NO_CALL = ["escalated", "low_mood", "paused", "declined"];

// "Getting lost": scheduled days without an answer, days an escalation may stay open.
export const LOST = { silent: 2, escalated: 2 };   // silent: scheduled call days without an answer

// Basket statuses in order.
export const BASKET = ["new", "ordered", "done"];
