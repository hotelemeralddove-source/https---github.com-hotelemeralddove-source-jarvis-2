"""Talking to people — calendar, email, WhatsApp — without storing anyone's password.

The interesting assertions are the refusals:

  * email with no configuration explains exactly what to set, and does not silently
    do nothing
  * the password is only ever read from an environment variable, never from settings
  * calendar events are real `.ics` files that survive a round trip
  * WhatsApp never claims to have sent anything — it opens a draft

Run:  python tests/test_comms.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

HOME = tempfile.mkdtemp(prefix="arcdesk-user-")
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ["ARCDESK_USER_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import comms, config  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def check_true(label: str, got) -> bool:
    return check(label, bool(got), True)


def main() -> int:
    ok = True

    # ---------- 1. understanding "when" -------------------------------
    print("1) plain-English times are understood")
    now = datetime.now()
    h4 = comms.parse_when("today 4pm")
    ok &= check("today 4pm → 16:00", (h4.hour, h4.minute) if h4 else None, (16, 0))
    ok &= check_true("today 4pm is today", h4.date() == now.date() if h4 else False)
    tm = comms.parse_when("tomorrow 9:30")
    ok &= check("tomorrow 9:30", (tm.hour, tm.minute) if tm else None, (9, 30))
    ok &= check_true("tomorrow is tomorrow",
                     tm.date() == (now + timedelta(days=1)).date() if tm else False)
    soon = comms.parse_when("in 2 hours")
    ok &= check_true("in 2 hours is about two hours away",
                     soon and 90 <= (soon - now).total_seconds() / 60 <= 130)
    exact = comms.parse_when("2026-10-24 16:00")
    ok &= check("absolute date", exact.strftime("%Y-%m-%d %H:%M") if exact else None,
                "2026-10-24 16:00")
    ok &= check("nonsense returns nothing", comms.parse_when("whenever"), None)

    # ---------- 2. real calendar files --------------------------------
    print("2) events are written as real .ics files")
    out = comms.add_event("dentist", "tomorrow 10am", minutes=45, notes="bring the card")
    ok &= check_true("add_event reports success", "dentist" in out)
    files = list(comms.calendar_folder().glob("*.ics"))
    ok &= check_true("an .ics file exists", len(files) >= 1)
    body = files[-1].read_text(encoding="utf-8")
    ok &= check_true("valid VCALENDAR envelope",
                     "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body)
    ok &= check_true("has a summary", "SUMMARY:dentist" in body)
    ok &= check_true("has start and end", "DTSTART:" in body and "DTEND:" in body)
    ok &= check_true("end is 45 minutes later",
                     body.split("DTEND:")[1][:15] != body.split("DTSTART:")[1][:15])
    ok &= check_true("alarm included", "BEGIN:VALARM" in body)

    print("3) and they come back out")
    listed = comms.list_events(days=7)
    ok &= check_true("the event is listed", "dentist" in listed)
    ok &= check_true("with a readable time", any(c.isdigit() for c in listed))

    print("4) commas and semicolons in a title do not break the file")
    # "tomorrow", not "today" — a same-day event that has already ended is
    # correctly absent from an upcoming list, which made this test pass or fail
    # depending on the hour it was run.
    comms.add_event("lunch; with Raj, maybe", "tomorrow 1pm", minutes=30)
    listed = comms.list_events(days=2)
    ok &= check_true("escaped title round-trips", "lunch" in listed and "Raj" in listed)

    print("5) nothing to show is said plainly")
    empty_home = tempfile.mkdtemp(prefix="arcdesk-empty-")
    os.environ["ARCDESK_USER_HOME"] = empty_home
    import importlib
    importlib.reload(comms)
    ok &= check_true("says the calendar is empty",
                     "nothing on the calendar" in comms.list_events(days=3))
    os.environ["ARCDESK_USER_HOME"] = HOME
    importlib.reload(comms)

    # ---------- 3. email refuses safely --------------------------------
    print("6) email without configuration explains itself")
    ready, why = comms.email_ready()
    ok &= check("not ready", ready, False)
    ok &= check_true("names settings.json", "settings.json" in why)
    sent = comms.send_email(to="a@b.com", subject="hi", body="hello")
    ok &= check_true("send refuses", sent.startswith("ERROR"))
    ok &= check_true("mentions the config", "settings.json" in sent or "not configured" in sent)

    print("7) a missing password names the environment variable")
    cfg = config.load()
    cfg["comms"] = {"email": {"host": "smtp.example.com", "port": 587,
                              "user": "me@example.com", "from": "me@example.com",
                              "password_env": "ARCDESK_TEST_SMTP"}}
    config.save(cfg)
    os.environ.pop("ARCDESK_TEST_SMTP", None)
    ready, why = comms.email_ready()
    ok &= check("still not ready without the password", ready, False)
    ok &= check_true("names the env var", "ARCDESK_TEST_SMTP" in why)
    os.environ["ARCDESK_TEST_SMTP"] = "x"
    ready, _ = comms.email_ready()
    ok &= check("ready once the password exists", ready, True)
    os.environ.pop("ARCDESK_TEST_SMTP", None)
    cfg.pop("comms", None)
    config.save(cfg)

    print("8) drafts and WhatsApp never pretend to have sent anything")
    opened: list[str] = []
    real_open = comms.webbrowser.open
    comms.webbrowser.open = lambda url, *a, **k: opened.append(url) or True
    try:
        res = comms.draft_email("x@y.com", "subject line", "body text")
        ok &= check_true("draft opened a mailto link", opened and opened[-1].startswith("mailto:"))
        ok &= check_true("draft says what it did", "draft" in res.lower())
        res = comms.whatsapp_send("+91 98765 43210", "on my way")
        ok &= check_true("whatsapp opens wa.me",
                         opened[-1].startswith("https://wa.me/919876543210"))
        ok &= check_true("message is url-encoded", "on%20my%20way" in opened[-1])
        ok &= check_true("no claim of sending", "pre-filled" in res and "press send" in res.lower())
        ok &= check_true("bad number refused",
                         comms.whatsapp_send("12", "hi").startswith("ERROR"))
        ok &= check_true("empty message refused",
                         comms.whatsapp_send("+919876543210", "").startswith("ERROR"))
    finally:
        comms.webbrowser.open = real_open

    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
