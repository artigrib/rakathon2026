"""E-mail an operations alert with the app's own SMTP settings (backend/.env). Never prints secrets.

  python3 -I deploy/ops/notify.py "subject" "body"
Recipient: OPS_EMAIL, else DEMO_EMAIL. Exits 0 even when e-mail is not configured (alerts must never break a job).
"""
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / "backend" / ".env"


def env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def main(subject: str, body: str) -> int:
    e = env()
    to = e.get("OPS_EMAIL") or e.get("DEMO_EMAIL")
    if os.getenv("NOTIFY_DRY_RUN") == "1":
        print(f"notify (dry run) to {'set' if to else 'nobody'}: {subject}\n{body}")
        return 0
    if not (e.get("SMTP_HOST") and e.get("SMTP_USER") and e.get("SMTP_PASSWORD") and to):
        print("notify: e-mail not configured, skipped:", subject)
        return 0
    m = EmailMessage()
    m["Subject"] = f"[jsemvcas.cz] {subject}"
    m["From"] = e.get("EMAIL_FROM") or e["SMTP_USER"]
    m["To"] = to
    m.set_content(body)
    try:
        with smtplib.SMTP(e["SMTP_HOST"], int(e.get("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            s.login(e["SMTP_USER"], e["SMTP_PASSWORD"])
            s.send_message(m)
        print("notify: sent:", subject)
    except Exception as ex:  # noqa: BLE001 – an alert that fails must not fail the job
        print("notify: failed:", type(ex).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
