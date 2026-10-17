"""Which visitor's demo a request belongs to. Each signed-in visitor has their own demo state (sessions.py);
callbacks from Twilio and the patient link carry the session id as ?s=… so they land in the same demo."""
from contextvars import ContextVar

from .settings import settings

session_id: ContextVar = ContextVar("session_id", default="")


def url(path: str) -> str:
    """Public URL for Twilio callbacks and patient links, tagged with the current visitor's session."""
    if not settings.public_url:
        return ""
    s = session_id.get()
    return f"{settings.public_url}{path}" + (f"?s={s}" if s else "")
