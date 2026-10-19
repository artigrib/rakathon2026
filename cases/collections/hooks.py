"""Collections hooks called by the core (backend/messages.py, backend/app.py).

  extra_placeholders  strategy-specific sentences for messages (never an amount or any detail of the debt)
  on_reply            records what a reply means: promise to pay (date, amount), plan choice, refinancing interest,
                      payment, channel opt-out, wrong contact, automation stop (dispute / vulnerability)
  on_tick             once per demo day: a promise kept (payment arrives) or broken, plan instalments, stale offers
  page                the secure page /p/{token}: identity verification first, then amount and the options

Case data per debtor (store.patch → /api/state decisions[id], visible in the web app as store.get(id).<field>):
  promises [{made, date, amount, status: open|kept|broken|replaced, via, dateGiven}], plan {kind, n, monthly, items},
  refi {status, made, example}, payments [{date, amount, via}], optout [channels] | "all", stopped {reason, date},
  contactInvalid {date, via}, verified (day), verifyFails, verifyLocked.
"""
import hashlib
import html
import json
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from cases.collections import dialog, strategy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = json.loads((HERE / "case.json").read_text(encoding="utf-8"))
GRACE_DAYS = 2          # a promise counts as broken this many days after its date
OFFER_DAYS = 7          # an offer without a choice goes to a person after this many days
VERIFY_TRIES = 3
PRODUCT = {"loan": "Spotřebitelský úvěr", "card": "Kreditní karta", "bnpl": "Nákup na splátky (BNPL)", "phone": "Telefon na splátky"}
# Demo: how likely a debtor of a segment keeps a promise (deterministic per debtor and promise, see _kept).
KEEP = {"forgetful": 0.9, "temporary": 0.7, "long_term": 0.55, "uncooperative": 0.3, "dispute": 0.5, "vulnerable": 0.5}


@lru_cache(maxsize=1)
def _records() -> dict:
    path = ROOT / MANIFEST["data"]
    if not path.exists():
        return {}
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["patients"]}


def record(pid: str) -> dict:
    return _records().get(pid, {})


def extra_placeholders(patient: dict, M: dict) -> dict:
    """{creditor} and the strategy's offer sentences. Deliberately nothing from the debt itself."""
    s = patient.get("strategy") or "reminder"
    P = M["parts"]
    return {"creditor": P["creditor"],
            **{k: P[k].get(s, P[k]["reminder"]) for k in ("offer_sms", "offer_email", "offer_voice")}}


# ---------- amounts ----------
def paid_total(d: dict) -> int:
    return sum(int(p.get("amount") or 0) for p in d.get("payments") or [])


def remaining(rec: dict, d: dict) -> int:
    return max(0, int(rec.get("outstanding") or 0) - paid_total(d))


def _int(v) -> int | None:
    try:
        n = int(float(str(v).replace(" ", "").replace(",", ".")))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _iso(v) -> str | None:
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        return None


# ---------- replies ----------
def _last(d: dict) -> dict:
    return (d.get("journey") or [{}])[-1]


def on_reply(pid: str, intent: str, extra: dict, store) -> None:
    d = store.get(pid)
    ev = _last(d)
    if ev.get("ignored"):  # the state machine did not accept it (e.g. a reply after the debt was paid): nothing to record
        return
    day = ev.get("date") or date.today().isoformat()
    via = ev.get("via") or "ui"
    rec = record(pid)
    extra = extra or {}
    fields = {}
    if extra.get("verification"):
        fields["verified" if verify(rec, extra["verification"]) else "verifyFailedBy"] = day
    if intent == "will_pay":
        when = extra.get("promise_when") or dialog.when_of(str(extra.get("promise_date") or ""))
        promised = _iso(extra.get("promise_date")) or dialog.resolve(when, day)
        amount = _int(extra.get("promise_amount")) or remaining(rec, d) or None
        promises = [{**p, "status": "replaced"} if p.get("status") == "open" else p for p in d.get("promises") or []]
        promises.append({"made": day, "date": promised or (date.fromisoformat(day) + timedelta(days=7)).isoformat(),
                         "dateGiven": bool(promised), "amount": amount, "status": "open", "via": via})
        fields["promises"] = promises
    elif intent == "plan_chosen":
        fields["plan"] = make_plan(rec, d, extra, day)
    elif intent in ("need_plan", "cannot_pay"):
        fields["offer"] = {"kind": "plan", "made": day}
    elif intent == "want_refi":
        fields["refi"] = {"status": "offered", "made": day, "example": strategy.refi_example(remaining(rec, d))}
    elif intent == "refi_accept":
        fields["refi"] = {**(d.get("refi") or {}), "status": "accepted", "accepted": day,
                          "example": (d.get("refi") or {}).get("example") or strategy.refi_example(remaining(rec, d))}
    elif intent == "paid":
        amount = _int(extra.get("amount")) or remaining(rec, d)
        fields["payments"] = [*(d.get("payments") or []), {"date": day, "amount": amount, "via": via}]
        fields["promises"] = [{**p, "status": "kept"} if p.get("status") == "open" else p for p in d.get("promises") or []]
    elif intent in ("dispute", "vulnerable"):
        fields["stopped"] = {"reason": intent, "date": day, "via": via}
    elif intent == "wrong_person":
        fields["contactInvalid"] = {"date": day, "via": via}
    elif intent == "channel_opt_out":
        chans = extra.get("channels") or [{"voice-ai": "voice", "voice-agent": "voice"}.get(via, via)]
        old = d.get("optout") if isinstance(d.get("optout"), list) else []
        fields["optout"] = sorted(set(old) | {c for c in chans if c in ("sms", "voice", "email", "whatsapp")})
    elif intent == "opt_out":
        fields["optout"] = "all"
    if fields:
        store.patch(pid, **fields)


def make_plan(rec: dict, d: dict, extra: dict, day: str) -> dict:
    amount = remaining(rec, d)
    first = (date.fromisoformat(day) + timedelta(days=7)).isoformat()
    if extra.get("kind") == "deferral":
        due = (date.fromisoformat(day) + timedelta(days=strategy.DEFERRAL_DAYS)).isoformat()
        return {"kind": "deferral", "n": 1, "monthly": amount, "made": day,
                "items": [{"due": due, "amount": amount, "status": "open"}]}
    n = _int(extra.get("n")) or 3
    items = [{**i, "status": "open"} for i in strategy.schedule(amount, n, first)]
    return {"kind": "plan", "n": n, "monthly": items[0]["amount"] if items else amount, "made": day, "items": items}


# ---------- demo clock ----------
def _kept(pid: str, key: str, seg: str) -> bool:
    """Deterministic demo outcome: does this debtor keep this promise / instalment?"""
    h = int(hashlib.sha256(f"{pid}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < KEEP.get(seg, 0.6)


def on_tick(day: str, store, transition, patients: dict) -> list:
    """Daily duties before the contact plan. Returns touches for the demo toast [{id, channel: "system", event}]."""
    done = []
    today = date.fromisoformat(day)
    for pid, d in list(store.decisions().items()):
        stage = d.get("stage")
        rec = patients.get(pid) or record(pid)
        seg = rec.get("segment", "temporary")
        if stage == "promise_to_pay":
            p = next((p for p in reversed(d.get("promises") or []) if p.get("status") == "open"), None)
            if not p:
                continue
            due = date.fromisoformat(p["date"])
            if today >= due and _kept(pid, p["made"] + p["date"], seg):
                amount = min(int(p.get("amount") or 0) or remaining(rec, d), remaining(rec, d)) or remaining(rec, d)
                payments = [*(d.get("payments") or []), {"date": day, "amount": amount, "via": "bank"}]
                promises = [{**q, "status": "kept", "keptOn": day} if q is p else q for q in d.get("promises")]
                store.patch(pid, payments=payments, promises=promises)
                left = remaining(rec, store.get(pid))
                transition(pid, "paid" if left <= 0 else "partial_paid", day, auto=True, amount=amount)
                if left > 0:
                    store.patch(pid, offer={"kind": "plan", "made": day, "rest": left})
                done.append({"id": pid, "channel": "system", "event": "paid" if left <= 0 else "partial_paid"})
            elif today > due + timedelta(days=GRACE_DAYS):
                promises = [{**q, "status": "broken", "brokenOn": day} if q is p else q for q in d.get("promises")]
                store.patch(pid, promises=promises)
                transition(pid, "broken", day, auto=True)
                done.append({"id": pid, "channel": "system", "event": "broken"})
        elif stage == "plan_active":
            plan = d.get("plan") or {}
            items = plan.get("items") or []
            changed, missed = False, False
            for i, it in enumerate(items):
                if it["status"] != "open":
                    continue
                due = date.fromisoformat(it["due"])
                if today >= due and _kept(pid, f"{plan.get('made')}#{i}", seg):
                    items[i] = {**it, "status": "paid", "paidOn": day}
                    d.setdefault("payments", []).append({"date": day, "amount": it["amount"], "via": "bank"})
                    changed = True
                    transition(pid, "instalment_paid", day, auto=True, amount=it["amount"], n=i + 1)
                    done.append({"id": pid, "channel": "system", "event": "instalment_paid"})
                elif today > due + timedelta(days=GRACE_DAYS):
                    items[i] = {**it, "status": "missed"}
                    changed = missed = True
                break  # one instalment at a time
            if changed:
                store.patch(pid, plan={**plan, "items": items}, payments=d.get("payments") or [])
            if missed:
                transition(pid, "plan_missed", day, auto=True)
                done.append({"id": pid, "channel": "system", "event": "plan_missed"})
            elif items and all(it["status"] == "paid" for it in items):
                transition(pid, "paid", day, auto=True)
                done.append({"id": pid, "channel": "system", "event": "paid"})
        elif stage in ("plan_offered", "refi_offered"):
            since = next((e["date"] for e in reversed(d.get("journey") or []) if e.get("stage") == stage and not e.get("ignored")), day)
            if (today - date.fromisoformat(since)).days >= OFFER_DAYS:
                transition(pid, "offer_expired", day, auto=True)
                done.append({"id": pid, "channel": "system", "event": "offer_expired"})
    return done


# ---------- identity verification ----------
def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def verify(rec: dict, answer: str) -> bool:
    """Birth date (12.3.1984, 12. 3. 1984, 1984-03-12, 12031984) or the last 4 digits of the contract number."""
    if not rec or not answer:
        return False
    a = answer.strip()
    dig = _digits(a)
    if len(dig) == 4 and _digits(rec.get("contract", ""))[-4:] == dig:
        return True
    born = rec.get("birthDate")
    if not born:
        return False
    y, m, d = born.split("-")
    m_ = re.fullmatch(r"\s*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})\s*", a)
    if m_:
        return (int(m_.group(1)), int(m_.group(2)), m_.group(3)) == (int(d), int(m), y)
    return a == born or dig == f"{d}{m}{y}"


# ---------- secure page /p/{token} ----------
STYLE = """<style>
  fieldset { border: 2px solid var(--hair); padding: 12px 16px 16px; margin: 0 0 18px; }
  legend { font-weight: 700; padding: 0 6px; }
  label { display: block; margin: 6px 0; }
  input[type=text], input[type=date], input[type=number], select { font: inherit; width: 100%; min-height: 52px; padding: 8px 12px; border: 2px solid var(--ink); background: var(--paper); color: var(--ink); border-radius: 0; }
  .rec { border-color: var(--red); }
  .tag { display: inline-block; font-size: 15px; font-weight: 600; color: var(--red); margin-bottom: 6px; }
  .err { color: var(--red); font-weight: 600; }
  .small { font-size: 16px; }
  form.inline { display: block; margin: 0; }
  .row2 { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }
  @media (max-width: 420px) { .row2 { grid-template-columns: 1fr; } }
</style>"""


def _fill(tpl: str, **kw) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(kw.get(m.group(1), m.group(0))), tpl)


def _messages() -> dict:
    return json.loads((HERE / "messages.cs.json").read_text(encoding="utf-8"))


def _word(n: int) -> str:
    return "splátky" if 2 <= n <= 4 else "splátka" if n == 1 else "splátek"


def _cz(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}. {int(m)}. {y}"


def _thanks(P: dict, text: str, title: str = "") -> str:
    return f'<h1>{title or P["thanks_title"]}</h1><div class="box"><p>{text}</p></div>{P["foot"]}'


def _verify_form(P: dict, error: str = "") -> str:
    err = f'<p class="err" role="alert">{error}</p>' if error else ""
    return f"""{STYLE}{P["head"]}
<form method="post">
  <input type="hidden" name="action" value="verify">
  <label for="v">{P["verify_label"]}</label>
  <input type="text" id="v" name="value" autocomplete="off" inputmode="text" required>
  {err}
  <button class="primary">{P["verify_button"]}</button>
</form>
<form method="post" class="inline"><input type="hidden" name="action" value="answer">
  <button class="quiet" name="answer" value="callback">{P["answers"][0]["label"]}</button></form>
<form method="post" class="inline"><input type="hidden" name="action" value="answer">{P["wrong"]}</form>
{P["foot"]}"""


def _full(P: dict, rec: dict, d: dict, day: str) -> str:
    amount = remaining(rec, d)
    s = rec.get("strategy") or "reminder"
    head = _fill(P["verified_head"], product=html.escape(PRODUCT.get(rec.get("product"), "Smlouva")), contract=html.escape(rec.get("contract", "")))
    box = _fill(P["amount"], amount=strategy.czk(amount), due=_cz(rec["dueSince"]) if rec.get("dueSince") else "")
    if d.get("stage") in ("dispute", "hardship_review"):  # a person handles it: no offers pushed, only a person
        return f"""{STYLE}{head}{box}<div class="box"><p>{P["answers"][2 if d.get("stage") == "dispute" else 1]["thanks"]}</p></div>
<form method="post"><input type="hidden" name="action" value="answer"><button name="answer" value="callback">{P["answers"][0]["label"]}</button></form>{P["foot"]}"""
    if amount <= 0:
        return _thanks(P, P["thanks"]["paid"])
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    pay = f"""<fieldset{{rec}}><legend>{P["pay_title"]}</legend>{{tag}}
  <form method="post"><input type="hidden" name="action" value="pay">
  <button class="primary">{_fill(P["pay_button"], amount=strategy.czk(amount))}</button></form>
  <p class="muted small">{P["pay_note"]}</p>
  <form method="post"><input type="hidden" name="action" value="promise">
  <p><b>{P["promise_title"]}</b></p>
  <div class="row2"><label>{P["promise_date"]}<input type="date" name="date" min="{tomorrow}" value="{(date.fromisoformat(day) + timedelta(days=7)).isoformat()}" required></label>
  <label>{P["promise_amount"]}<input type="number" name="amount" min="100" max="{amount}" value="{amount}" required></label></div>
  <button>{P["promise_button"]}</button></form></fieldset>"""
    opts = strategy.plan_options(amount)
    plans = "".join(f'<button name="n" value="{o["n"]}">{_fill(P["plan_option"], n=o["n"], word=_word(o["n"]), monthly=strategy.czk(o["monthly"]))}</button>' for o in opts)
    due30 = _cz((date.fromisoformat(day) + timedelta(days=strategy.DEFERRAL_DAYS)).isoformat())
    plan = f"""<fieldset{{rec}}><legend>{P["plan_title"]}</legend>{{tag}}
  <form method="post"><input type="hidden" name="action" value="plan">{plans}</form>
  <form method="post"><input type="hidden" name="action" value="deferral"><button>{_fill(P["deferral"], due_date=due30)}</button></form>
  <p class="muted small">{P["plan_note"]}</p></fieldset>"""
    ex = strategy.refi_example(amount)
    refi = f"""<fieldset{{rec}}><legend>{P["refi_title"]}</legend>{{tag}}
  <p>{_fill(P["refi_example"], principal=strategy.czk(ex["principal"]), months=ex["months"], monthly=strategy.czk(ex["monthly"]),
              rate=str(ex["rate"]).replace(".", ","), rpsn=str(ex["rpsn"]).replace(".", ","), total=strategy.czk(ex["total"]))}</p>
  <p class="muted small">{P["refi_disclaimer"]}</p>
  <form method="post"><input type="hidden" name="action" value="refi"><button>{P["refi_button"]}</button></form></fieldset>"""
    order = {"reminder": ["pay", "plan", "refi"], "plan": ["plan", "pay", "refi"], "refi": ["refi", "plan", "pay"],
             "supervisor": ["pay", "plan", "refi"], "human": ["pay", "plan", "refi"]}[s]
    blocks = {"pay": pay, "plan": plan, "refi": refi}
    if s == "reminder":
        order = ["pay", "plan"]  # forgetful: keep it simple
    tag = f'<span class="tag">{P["recommended"]}</span>'
    body = "".join(blocks[k].replace("{rec}", ' class="rec"' if i == 0 else "").replace("{tag}", tag if i == 0 else "") for i, k in enumerate(order))
    others = "".join(f'<button{" class=" + chr(34) + a["class"] + chr(34) if a.get("class") else ""} name="answer" value="{a["value"]}">{a["label"]}</button>' for a in P["answers"])
    chans = "".join(f'<option value="{k}">{v}</option>' for k, v in P["channels"].items())
    other = f"""<fieldset><legend>{P["other_title"]}</legend>
  <form method="post"><input type="hidden" name="action" value="answer">{others}</form>
  <form method="post"><input type="hidden" name="action" value="channel"><label>{P["channel_stop"]}<select name="channel">{chans}</select></label><button class="quiet">OK</button></form>
  </fieldset>"""
    return f"{STYLE}{head}{box}{body}{other}{P['foot']}"


def page(pid: str, rec: dict, form: dict | None, store, day: str) -> dict:
    """The secure page. Nothing about the debt is shown until the identity is verified (on this demo day)."""
    M = _messages()
    P = M["page"]
    rec = rec or record(pid)
    d = store.get(pid)
    title = P["title"]
    if d.get("stage") == "wrong_contact" or not rec:
        return {"html": P["invalid"], "title": title}
    if d.get("stage") == "paid":
        return {"html": _thanks(P, P["thanks"]["paid"]), "title": title}
    if d.get("verifyLocked"):
        return {"html": P["verify_locked"] + P["foot"], "title": title}
    verified = d.get("verified") == day
    form = form or {}
    action = form.get("action")
    if action == "verify":
        if verify(rec, form.get("value", "")):
            store.patch(pid, verified=day, verifyFails=0)
            return {"html": _full(P, rec, store.get(pid), day), "title": title}
        fails = int(d.get("verifyFails") or 0) + 1
        if fails >= VERIFY_TRIES:
            store.patch(pid, verifyFails=fails, verifyLocked=day)
            return {"html": P["verify_locked"] + P["foot"], "title": title,
                    "reply": {"event": "human", "intent": "unclear", "extra": {"reason": "verification_failed"}}}
        store.patch(pid, verifyFails=fails)
        return {"html": _verify_form(P, P["verify_error"]), "title": title}
    if action == "answer" and form.get("answer") == "wrong":
        return {"html": _thanks(P, P["wrong_thanks"], "Omlouváme se"), "title": title, "reply": {"event": "wrong_person", "intent": "wrong_person"}}
    if action == "answer" and form.get("answer") == "callback":
        a = P["answers"][0]
        return {"html": _thanks(P, a["thanks"]), "title": title, "reply": {"event": a["event"], "intent": a["intent"]}}
    if not verified:
        return {"html": _verify_form(P), "title": title}
    if not action:
        return {"html": _full(P, rec, d, day), "title": title}
    amount = remaining(rec, d)
    T = P["thanks"]
    if action == "pay":
        return {"html": _thanks(P, T["paid"]), "title": title, "reply": {"event": "paid", "intent": "paid", "extra": {"amount": amount}}}
    if action == "promise":
        when = _iso(form.get("date")) or (date.fromisoformat(day) + timedelta(days=7)).isoformat()
        if when <= day:
            when = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        amt = min(_int(form.get("amount")) or amount, amount)
        return {"html": _thanks(P, _fill(T["promise"], amount=strategy.czk(amt), date=_cz(when))), "title": title,
                "reply": {"event": "will_pay", "intent": "will_pay", "extra": {"promise_date": when, "promise_amount": amt}}}
    if action in ("plan", "deferral"):
        extra = {"kind": action, "n": _int(form.get("n")) or 3}
        plan = make_plan(rec, d, extra, day)
        text = (_fill(T["deferral"], first=_cz(plan["items"][0]["due"])) if action == "deferral"
                else _fill(T["plan"], n=plan["n"], word=_word(plan["n"]), monthly=strategy.czk(plan["monthly"]), first=_cz(plan["items"][0]["due"])))
        return {"html": _thanks(P, text), "title": title, "reply": {"event": "plan_chosen", "intent": "plan_chosen", "extra": extra}}
    if action == "refi":
        return {"html": _thanks(P, T["refi"]), "title": title, "reply": {"event": "refi_accept", "intent": "refi_accept"}}
    if action == "channel" and form.get("channel") in P["channels"]:
        c = form["channel"]
        return {"html": _thanks(P, _fill(P["channel_stop_thanks"], channel=P["channels"][c])), "title": title,
                "reply": {"event": "channel_opt_out", "intent": "channel_opt_out", "extra": {"channels": [c]}}}
    if action == "answer":
        a = next((a for a in P["answers"] if a["value"] == form.get("answer")), None)
        if a:
            return {"html": _thanks(P, a["thanks"]), "title": title, "reply": {"event": a["event"], "intent": a["intent"]}}
    return {"html": _full(P, rec, d, day), "title": title}
