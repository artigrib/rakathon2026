// Patient journey state machine, same table as the backend (content/journey.json).
let J = null;

export async function loadJourney(url = "content/journey.json") {
  J = await (await fetch(url)).json();
}

export const INITIAL = () => J.initial;

/** Target state for an event, or null when the event is not allowed now (it is then ignored). */
export function next(state, event, refusals = 0) {
  const target = J.transitions[state || J.initial]?.[event];
  if (!target) return null;
  if (event === J.soft_decline.event && refusals === 0) return J.soft_decline.first_to;
  return target;
}

export const allowed = (state, event) => !!J.transitions[state || J.initial]?.[event];

/** Work-queue section of a stage (null = nothing to do, the patient is done). */
export const sectionOf = (state) => J.states[state || J.initial]?.section ?? null;

export const isFinal = (state) => !!J.states[state || J.initial]?.final;

/** Number of refusals already recorded (the first one is soft). */
export const refusals = (journey = []) => journey.filter((e) => !e.ignored && (e.intent === "declined" || e.intent === "opt_out")).length;
