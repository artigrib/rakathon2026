"""Jsem v pořádku contact ladder of one check-in (days from the first call of the cycle):

  0 call (in the senior's window)  →  0 call again (retry, about 2 h later)  →  1 SMS to the relative (2x no answer)
  →  1 call again  →  2 the social worker visits (3x no answer, a person takes over: event "visit" → escalated)

Any answer stops the ladder (every reply stage is terminal in case.json). Every reply stage also closes the cycle,
so the next scheduled check-in starts again from the first call (Plan.cycle_stages). The demo clock moves by days,
so the same-day retry goes out on the next tick; in production the cron runs every 15 minutes."""
from backend.plan import Plan, Step

REPLY_STAGES = frozenset({"enrolled", "ok", "needs_help", "low_mood", "callback", "escalated", "resolved", "paused"})

PLAN = Plan(
    steps=(
        Step(0, "voice", "CHECKIN"),
        Step(0, "voice", "RETRY"),
        Step(1, "sms", "RELATIVE"),
        Step(1, "voice", "RETRY"),
        Step(2, "visit"),
    ),
    pause_days=0,
    restart_variant="CHECKIN",
    pause_stage="",
    human="visit",
    stop_stages=frozenset({"escalated", "paused"}),
    cycle_stages=REPLY_STAGES,
)
