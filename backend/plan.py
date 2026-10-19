"""Contact plan shape (cadence). Cases define their own PLAN in cases/<id>/cadence.py; the algorithm is backend/cadence.py."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    day: int
    channel: str          # sms | voice | whatsapp | email | <Plan.human>
    variant: str = "REMINDER"


@dataclass(frozen=True)
class Plan:
    steps: tuple = field(default_factory=tuple)
    pause_days: int = 90                  # after a reply in pause_stage
    restart_variant: str = "MOTIVATION"   # first touch of a new cycle after the pause
    pause_stage: str = "not_now"          # stage that pauses the plan ("" = no pause)
    human: str = "nurse"                  # step channel meaning "a person takes over": fires this journey event
    stop_stages: frozenset = frozenset()  # stages after which nothing automatic follows (besides terminal_reply_stages)
