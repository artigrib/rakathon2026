"""Point a Twilio number at this service: voice webhook and status callback only, SMS settings stay as they are.

  python -m assistant.provision +19804731320          # show what would change
  python -m assistant.provision +19804731320 --apply  # change it; the old values are printed and saved first
"""
import base64
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

FIELDS = ("voice_url", "voice_method", "voice_fallback_url", "status_callback", "status_callback_method", "sms_url")


def _api(path: str, form: dict = None) -> dict:
    sid, tok = config.env("TWILIO_ACCOUNT_SID"), config.env("TWILIO_AUTH_TOKEN")
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}",
                                 data=urllib.parse.urlencode(form).encode() if form else None,
                                 headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main(argv: list) -> int:
    number = config.normalize_phone(argv[0]) if argv else ""
    if not number or not config.public_url():
        print(__doc__)
        return 2
    found = _api("/IncomingPhoneNumbers.json?" + urllib.parse.urlencode({"PhoneNumber": number})).get("incoming_phone_numbers", [])
    if not found:
        print(f"{number} is not on this Twilio account")
        return 1
    n = found[0]
    old = {k: n.get(k) for k in FIELDS}
    new = {"VoiceUrl": f"{config.public_url()}/twilio/inbound", "VoiceMethod": "POST",
           "StatusCallback": f"{config.public_url()}/twilio/status", "StatusCallbackMethod": "POST"}
    print("now:", json.dumps(old, indent=1))
    print("set:", json.dumps(new, indent=1))
    if "--apply" not in argv:
        print("dry run, add --apply")
        return 0
    Path(config.env("ASSISTANT_DB", "/data/assistant.db")).with_name(f"number-{number}-{int(time.time())}.json").write_text(json.dumps(old))
    _api(f"/IncomingPhoneNumbers/{n['sid']}.json", new)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
