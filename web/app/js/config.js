// App configuration: everything that is a product decision, not code.

export const DATA_URL = "data/patients.json";
export const MESSAGES_URL = "content/messages.cs.json";
export const DEFAULT_GP = "VPL-0142";
export const NO_RESPONSE_DAYS = 14;
export const STORAGE_KEY = "plice-vcas:v2";

export const CHANNELS = ["portal", "sms", "voice", "email", "letter"];

// Work queue of the practice, in order of urgency. One section = one kind of work.
export const SECTIONS = ["invite", "replied", "doctor", "results"];
// Patients view filters.
export const FILTERS = ["all", "todo", "running", "done", "excluded"];

// Patient journey after the invitation (doctor 16.10.: patient books any pneumologist himself; result comes on paper).
export const JOURNEY = [
  { key: "sent", stages: ["sent", "nurse_call"] },
  { key: "replied", stages: ["interested", "callback"] },
  { key: "booked", stages: ["booked"] },
  { key: "ldct", stages: ["ldct"] },
  { key: "result", stages: ["result"] },
];
// Patient replies that the backend will receive via webhooks; in the demo they are simulated from the row.
export const REPLIES = ["interested", "booked", "callback", "not_now"];
// Next step after an LDCT result. negative → repeat after 2 years (doctor); others are decided by the pneumologist.
export const RESULTS = { negative: { nextDays: 730 }, indeterminate: { nextDays: null }, positive: { nextDays: null } };

export const CRITERIA = "55–74 let, kuřák nebo bývalý kuřák, alespoň 20 balíčkoroků, bez CT hrudníku za posledních 30 dní";

// Practice contact shown in patient messages (deck slide 20). In production this comes from the GP's profile
// after login; leave phone empty to omit it from the text.
export const PRACTICES = {
  "VPL-0142": { phone: "" },
};

// Backend (FastAPI). When the page is served by the backend, the app switches to live mode automatically;
// as a static page (artifact) it keeps working locally with simulated sending.
export const API_BASE = "";
export const POLL_MS = 3000;
