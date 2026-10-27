"""Talking to people — email, calendar, WhatsApp.

The rule for this module: **no account is stored by Arc Desk, ever.** A password in a
settings file is a password in a backup, in a screenshot, in a chat with support. So:

  * **Email** uses SMTP with a password read from an *environment variable* named in
    settings. If it is not there, the tool says exactly what to set instead of failing
    mysteriously. Gmail needs an app password (2FA on) — the tool says that too.
  * **Calendar** writes and reads plain `.ics` files in your own folder, and can read
    a read-only subscription URL. No OAuth, no Google project, no keys. An `.ics` file
    opens in whatever calendar you already use.
  * **WhatsApp** opens `wa.me` with the message pre-filled in your own browser or
    desktop app. You press send. That is deliberate: automating someone's personal
    messenger with stored session cookies is how assistants get accounts banned.

Everything here is offline until you explicitly configure an address, and every
sending tool is `confirm=True` in the registry — ARC will not message anyone without
you seeing the recipient and the text first.
"""
from __future__ import annotations

# `smtplib` costs ~40 ms to import and is only needed at the moment mail is actually sent.
# On a cold start that is 40 ms of the double-click spent on an import most sessions never
# touch, so it is loaded on first use.
def _smtplib():
    import smtplib
    return smtplib

import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from . import config


# ------------------------------------------------------------------ config
def _comms_cfg() -> dict:
    return (config.load().get("comms") or {})


def _email_cfg() -> dict:
    return (_comms_cfg().get("email") or {})


def _calendar_cfg() -> dict:
    return (_comms_cfg().get("calendar") or {})


def email_ready() -> tuple[bool, str]:
    """(ready, reason) — reason is phrased for the user, not for a log."""
    e = _email_cfg()
    if not e.get("host") or not e.get("from"):
        return False, ("email is not configured yet. Add host, port, user and from under "
                       "\"comms\": {\"email\": {...}} in settings.json — INSTALL.md has a "
                       "printable example. Nothing is stored until you do.")
    env = e.get("password_env") or "ARCDESK_SMTP_PASSWORD"
    if not os.environ.get(env):
        return False, (f"the SMTP password is missing. Set the environment variable {env} "
                       f"(setx {env} \"your-app-password\") and restart Arc Desk. "
                       "Gmail needs an app password with 2FA enabled.")
    return True, ""


# ------------------------------------------------------------------ email
def send_email(to: str = "", subject: str = "", body: str = "",
               attachment: str = "") -> str:
    """Send one plain-text email. Confirm-gated in the registry."""
    to = (to or "").strip()
    if not to or "@" not in to:
        return "ERROR: I need a valid recipient address"
    if not (subject or body):
        return "ERROR: an email needs a subject or a body"
    ready, why = email_ready()
    if not ready:
        return f"ERROR: {why}"

    e = _email_cfg()
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = e.get("from")
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body or "")
    if attachment:
        p = Path(os.path.expanduser(attachment))
        if not p.is_file():
            return f"ERROR: attachment {p} does not exist"
        if p.stat().st_size > 10 * 1024 * 1024:
            return "ERROR: attachment is larger than 10 MB"
        msg.add_attachment(p.read_bytes(), maintype="application", subtype="octet-stream",
                           filename=p.name)

    host = e.get("host")
    port = int(e.get("port") or 587)
    user = e.get("user") or e.get("from")
    password = os.environ.get(e.get("password_env") or "ARCDESK_SMTP_PASSWORD", "")
    try:
        if int(port) == 465:
            server = _smtplib().SMTP_SSL(host, port, timeout=20,
                                      context=ssl.create_default_context())
        else:
            server = _smtplib().SMTP(host, port, timeout=20)
            server.ehlo()
            if e.get("use_tls", True):
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
        server.login(user, password)
        server.send_message(msg)
        server.quit()
    except Exception as exc:
        return (f"ERROR: sending failed — {type(exc).__name__}: {exc}. "
                "Check the SMTP host/port and that the app password is current.")
    return f"email sent to {to}" + (f" with {Path(attachment).name}" if attachment else "")


def draft_email(to: str = "", subject: str = "", body: str = "") -> str:
    """Open the default mail client with everything filled in — no password needed."""
    url = ("mailto:" + urllib.parse.quote(to or "")
           + "?subject=" + urllib.parse.quote(subject or "")
           + "&body=" + urllib.parse.quote(body or ""))
    try:
        webbrowser.open(url)
        return f"opened your mail app with a draft to {to or '(nobody yet)'}"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ calendar
def calendar_folder() -> Path:
    raw = _calendar_cfg().get("folder") or "Calendar"
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home()) / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ics_escape(text: str) -> str:
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _ics_unescape(text: str) -> str:
    return (str(text or "").replace("\\n", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def parse_when(text: str) -> datetime | None:
    """Understand 'today 4pm', 'tomorrow 09:30', '2026-10-24 16:00', 'in 2 hours'."""
    t = (text or "").strip().lower()
    if not t:
        return None
    now = datetime.now().replace(second=0, microsecond=0)

    m = re.search(r"in\s+(\d+)\s*(min|minute|hour|hr|day)s?", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = (timedelta(minutes=n) if unit.startswith("min") else
                 timedelta(hours=n) if unit.startswith("h") else timedelta(days=n))
        return now + delta

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
    base = now
    if "tomorrow" in t:
        base = now + timedelta(days=1)
    elif re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)", t):
        for i, name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
            if name in t:
                ahead = (i - now.weekday()) % 7 or 7
                base = now + timedelta(days=ahead)
                break
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3) == "pm":
            hour += 12
        minute = int(m.group(2) or 0)
        return base.replace(hour=hour, minute=minute)

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ t](\d{1,2}):(\d{2})", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)))

    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        return base.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2)))
    return None


def add_event(title: str = "", when: str = "", minutes: int = 30, notes: str = "") -> str:
    """Create a real .ics file and open it in the system calendar."""
    title = (title or "").strip()
    if not title:
        return "ERROR: what should the event be called?"
    start = parse_when(when) or (datetime.now().replace(second=0, microsecond=0)
                                 + timedelta(minutes=5))
    length = max(5, min(int(minutes or 30), 24 * 60))
    end = start + timedelta(minutes=length)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"arc-{int(time.time())}-{abs(hash(title)) % 10000}@arcdesk.local"
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Arc Desk//JARVIS//EN", "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(title)}",
        (f"DESCRIPTION:{_ics_escape(notes)}" if notes else ""),
        "BEGIN:VALARM", "TRIGGER:-PT10M", "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape(title)}", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", ""])
    path = calendar_folder() / f"arc_{start.strftime('%Y%m%d_%H%M')}_{abs(hash(title)) % 1000}.ics"
    try:
        path.write_text(body, encoding="utf-8", newline="")
    except Exception as exc:
        return f"ERROR: could not write the event — {type(exc).__name__}: {exc}"
    opened = ""
    try:
        if os.name == "nt":
            os.startfile(str(path))          # noqa: S606 — the user asked for it
            opened = " and opened it in your calendar"
    except Exception:
        opened = ""
    return (f"event '{title}' on {start:%a %d %b %H:%M}-{end:%H:%M} saved to "
            f"{path.name}{opened}")


def _parse_ics(text: str) -> list[dict]:
    events: list[dict] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.S):
        fields: dict[str, str] = {}
        for line in block.replace("\r\n", "\n").splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.split(";")[0].upper()
            fields[key] = val.strip()
        start_raw = fields.get("DTSTART", "")
        start = None
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
            try:
                start = datetime.strptime(start_raw, fmt)
                break
            except ValueError:
                continue
        if start is None:
            continue
        if start_raw.endswith("Z"):
            start = start.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        events.append({"title": _ics_unescape(fields.get("SUMMARY", "(untitled)")),
                       "start": start, "location": _ics_unescape(fields.get("LOCATION", ""))})
    return events


def _fetch_ics(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def list_events(days: int = 7, limit: int = 15) -> str:
    """Today and the next N days, from local .ics files and any subscribed URLs."""
    days = max(1, min(int(days or 7), 90))
    now = datetime.now()
    horizon = now + timedelta(days=days)
    events: list[dict] = []

    for path in calendar_folder().glob("*.ics"):
        try:
            events.extend(_parse_ics(path.read_text(encoding="utf-8", errors="replace")))
        except Exception:
            continue
    for url in (_calendar_cfg().get("ics_urls") or []):
        events.extend(_parse_ics(_fetch_ics(url)))

    upcoming = sorted((e for e in events if e["start"] and now <= e["start"] <= horizon),
                      key=lambda e: e["start"])[:max(1, min(int(limit or 15), 50))]
    if not upcoming:
        return f"nothing on the calendar in the next {days} day(s)"
    lines = []
    for e in upcoming:
        when = e["start"].strftime("%a %d %b %H:%M")
        lines.append(f"{when} — {e['title']}" + (f" ({e['location']})" if e["location"] else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------ WhatsApp
def whatsapp_send(number: str = "", message: str = "") -> str:
    """Open WhatsApp with the message written. Sending stays in your hands."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) < 8:
        return "ERROR: give me a phone number with country code, e.g. +91 98765 43210"
    if not message:
        return "ERROR: what should I say?"
    url = f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"
    try:
        webbrowser.open(url)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    return (f"opened WhatsApp for +{digits} with the message pre-filled. "
            "Press send there — I will not send messages from your account on my own.")
