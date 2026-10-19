"""Screening contact plan (days from the first invitation of the current cycle):
  0 SMS  →  3 voice call  →  5 voice call (other time of day)  →  8 WhatsApp  →  12 nurse calls personally
Stops immediately on any reply. "Not now" pauses the plan, then a new cycle starts with a motivating text."""
from backend.plan import Plan, Step

PLAN = Plan(
    steps=(
        Step(0, "sms", "FIRST_INVITE"),
        Step(3, "voice"),
        Step(5, "voice"),
        Step(8, "whatsapp"),
        Step(12, "nurse"),
    ),
    pause_days=90,
    restart_variant="MOTIVATION",
    pause_stage="not_now",
    human="nurse",
    stop_stages=frozenset({"nurse_call"}),
)
