"""Diagnosis — "idhu enna error da": read the error, name it, explain it, fix it.

The single most common thing a person wants from an assistant at 11 p.m. is not
"write me a poem". It is *"what is this thing on my screen telling me?"*

This module is deliberately **not** a language model. It is a curated set of error
signatures, each matched against the literal text on the screen, each carrying:

    means   what the error is actually saying
    why     the causes, most likely first
    steps   what to do, in order, with the exact Windows/Linux thing to click
    arc     what ARC itself can do about it (only when that is genuinely true)
    sure    how confident the pattern is: "certain" for a documented code,
            "likely" for a wording that varies between versions

Three honesty rules, and this file is built around them:

1. **Quote before you explain.** Every answer starts by echoing the exact line that
   was read, so the user can see what ARC saw. If OCR misread it, they can tell.
2. **No match is a real answer.** An unrecognised error gets the text back, a plain
   "I do not recognise this one", and a search — never an invented cause dressed up
   as a diagnosis. A wrong fix at midnight is worse than no fix.
3. **Pattern, not prophecy.** "Documented for Windows 0xc000007b" is a fact. "Your
   specific DLL is corrupt" is a guess, and is written as one.

It reads, in order: text you give it → your clipboard → the screen (OCR).
"""
from __future__ import annotations

import re
import shutil
import subprocess

from . import quiet
import sys

IS_WIN = sys.platform == "win32"

MAX_CHARS = 4000                     # a screen's worth of text, not a whole log file
MAX_LINES = 6                        # how many error-ish lines are shown back


# --------------------------------------------------------------------------
# The signature table.
#
# `keys` are case-insensitive regexes. A line only has to match ONE of them; a
# signature with several keys that hit scores higher, so "0xc000007b" beats a
# generic "could not start". `weight` breaks ties between overlapping families
# (a Python traceback is a better fit than "permission denied" alone).
# --------------------------------------------------------------------------
SIGNATURES: list[dict] = [
    # ---------------- Windows: application start-up failures ---------------
    dict(
        id="win_bad_image",
        keys=[r"0xc000007b", r"the application was unable to start correctly"],
        title="Windows could not start the program (0xc000007b)",
        sure="certain",
        means="Windows found the program, but a library it needs is the wrong "
              "bit-width or version — a 32-bit program loading a 64-bit DLL, or the "
              "wrong Visual C++ runtime. The program did not run at all.",
        why=["The program is 32-bit and a 64-bit DLL of the same name is on the PATH.",
             "The Microsoft Visual C++ Redistributable it needs is missing or broken.",
             "A half-finished install or a copied game folder that lost its DLLs."],
        steps=["Reinstall the program from its own installer (not by copying files).",
               "Install the matching Visual C++ Redistributable — x86 for a 32-bit "
               "program, x64 for a 64-bit one. Both, if you are unsure.",
               "If it started working before and now does not: Windows Update → "
               "'View update history' → uninstall the newest update, retest."],
        arc="say 'system report' — it shows whether the disk has room for a reinstall.",
    ),
    dict(
        id="win_smart_screen",
        keys=[r"windows protected your pc", r"unrecognized app", r"more info.{0,40}run anyway"],
        title="SmartScreen blocked an app it has not seen before",
        sure="certain",
        means="This is Windows being careful about a file it cannot vouch for. It is "
              "not a virus verdict — it means 'unknown publisher', which is also what "
              "a small self-built tool looks like.",
        why=["The program is unsigned (no paid code-signing certificate).",
             "Few people have downloaded that exact file, so SmartScreen has no "
             "reputation for it.",
             "It genuinely is malware — which is why this dialog exists."],
        steps=["Only continue if you know where the file came from. If you do not, "
               "delete it instead.",
               "If you trust it: 'More info' → 'Run anyway'.",
               "Check the file first: right-click → Properties → Digital Signatures, "
               "or upload it to VirusTotal in a browser."],
        arc="say 'secure phishing' with a link you were sent, to look for the usual traps.",
    ),
    dict(
        id="win_access_denied",
        keys=[r"0x80070005", r"\baccess is denied\b", r"you need permission to perform",
              r"requires elevation"],
        title="Access denied (0x80070005)",
        sure="certain",
        means="Windows refused the operation because your account does not have the "
              "right to that file, folder, registry key or service. Nothing was damaged.",
        why=["The file is inside a protected folder (Program Files, Windows, another "
             "user's profile).",
             "The file is read-only, or owned by an account that is not yours.",
             "An antivirus 'Controlled folder access' rule is holding it."],
        steps=["Move or copy the file into your own Documents folder and edit it there.",
               "Right-click the app → 'Run as administrator' — only if you trust it.",
               "Check the file is not read-only: right-click → Properties → uncheck "
               "'Read-only'.",
               "If it is an antivirus block: Windows Security → Protection history."],
        arc="nothing here — JARVIS never asks for admin, so it cannot bypass this either.",
    ),
    dict(
        id="win_not_found",
        keys=[r"windows cannot find", r"is not recognized as an internal or external command",
              r"cannot find the (file|path) specified"],
        title="The file or command is not where it was expected",
        sure="certain",
        means="The name was spelled right as far as Windows is concerned, but nothing "
              "with that name exists on the PATH or in that folder.",
        why=["The program is not installed, or was uninstalled and the shortcut remains.",
             "It is installed but its folder is not on the PATH.",
             "The current directory is not the one you think it is."],
        steps=["For a command line: `where <name>` (Windows) or `which <name>` (Linux) "
               "tells you if it exists at all.",
               "Open a new terminal — PATH changes only apply to new windows.",
               "For a shortcut: right-click → Properties → check the 'Target' path."],
        arc="say 'find <name>' — JARVIS searches your indexed folders by filename.",
    ),
    dict(
        id="win_disk_full",
        keys=[r"not enough space", r"insufficient (disk|storage)", r"disk is full",
              r"0x80070070", r"no space left on device"],
        title="The disk is full",
        sure="certain",
        means="The write failed because the target drive has no free space. This one "
              "is almost never a corruption problem.",
        why=["Large downloads, game installs, or video renders filled the drive.",
             "Windows Update cache, hibernation file, or the Recycle Bin.",
             "A small SSD split into two partitions with the wrong one full."],
        steps=["Settings → System → Storage → 'Temporary files' removes the safe ones.",
               "Empty the Recycle Bin.",
               "Move big videos to another drive. If you ask JARVIS, it will not delete "
               "your files — it will tell you the sizes and let you choose."],
        arc="say 'system report' — it shows free space per drive, measured right now.",
    ),
    dict(
        id="win_generic_code",
        keys=[r"\b0x[0-9a-f]{8}\b"],
        fallback=True,
        title="Windows reported an error code",
        sure="likely",
        means="A numeric status code. The code is the useful part — Windows error codes "
              "in the 0x8007 range are Win32 errors (the last four hex digits are the "
              "real reason, e.g. 0x80070005 → 5 = access denied).",
        why=["Whatever operation you were doing was refused or interrupted.",
             "Often a permissions, network, or missing-component problem."],
        steps=["Search the exact code with the program name — the four trailing hex "
               "digits are the part that identifies it.",
               "Reboot once, then retry the exact same action to see if it is repeatable.",
               "Windows: Event Viewer → Windows Logs → System, sorted by time."],
        arc="paste the full message and JARVIS will match it against its known codes.",
    ),
    dict(
        id="win_bsod",
        keys=[r"stop code", r"your pc ran into a problem", r"0x000000[0-9a-f]{2}",
              r"bugcheck"],
        title="Windows crashed (a stop code / blue screen)",
        sure="certain",
        means="The kernel stopped on purpose because continuing could damage data. "
              "The stop code names the class of failure; the dump file names the driver.",
        why=["A device driver (often graphics, Wi-Fi, or a USB device) faulted.",
             "Failing RAM or an unstable overclock/XMP profile.",
             "A storage driver error on a nearly-dead SSD."],
        steps=["Write the stop code down; it is the only real clue.",
               "If it repeats after a hardware change, undo that change first.",
               "Run `sfc /scannow` then `DISM /Online /Cleanup-Image /RestoreHealth` "
               "in an admin terminal.",
               "For memory: Windows Memory Diagnostic (mdsched.exe), run overnight."],
        arc="say 'system report' for RAM/disk pressure, though a crash dump needs a human.",
    ),
    dict(
        id="win_service",
        keys=[r"the .{2,40} service .{0,30}failed to start", r"error 1053",
              r"service did not respond"],
        title="A Windows service would not start",
        sure="certain",
        means="The service was asked to start and did not report 'running' in time, or "
              "exited immediately. Error 1053 is specifically a timeout.",
        why=["Its login account or password changed (common after a password change).",
             "A dependency service is stopped or disabled.",
             "The executable was moved, quarantined by antivirus, or is corrupt."],
        steps=["services.msc → right-click the service → Properties → 'Log On' tab → "
               "check the account.",
               "Same dialog → 'Dependencies' tab → start those first.",
               "Event Viewer → Windows Logs → Application, for the real exception text."],
        arc="nothing — starting services needs admin, which JARVIS refuses to request.",
    ),
    dict(
        id="win_update_fail",
        keys=[r"0x8024[0-9a-f]{4}", r"0x800f[0-9a-f]{4}", r"we couldn.t install some updates",
              r"windows update.{0,30}failed"],
        title="Windows Update failed",
        sure="likely",
        means="The update package was rejected, could not be downloaded cleanly, or an "
              "in-use file blocked the swap. The system is usually still fine.",
        why=["A corrupted update cache, or disk space below ~10 GB.",
             "A third-party antivirus holding a system file.",
             "The update is for a component that is already at a newer build."],
        steps=["Settings → Windows Update → 'Troubleshoot'.",
               "Free at least 10 GB, then retry.",
               "The reliable manual route: stop 'Windows Update' service, rename "
               "C:\\Windows\\SoftwareDistribution to SoftwareDistribution.old, start it "
               "again, retry. (Renaming, not deleting — reversible.)"],
        arc="nothing automatic — JARVIS does not touch Windows components by design.",
    ),

    # ---------------- Python / developer ----------------
    dict(
        id="py_traceback",
        keys=[r"traceback \(most recent call last\)", r"^\s*File \".+\", line \d+"],
        # the frame is always less useful than the exception class at the bottom
        fallback=True,
        title="A Python program raised an exception",
        sure="certain",
        means="The last line of the traceback is the actual error; everything above it "
              "is the path that got there. Read it bottom-up.",
        why=["The final line names the type: ModuleNotFoundError (missing package), "
             "FileNotFoundError (wrong path), KeyError (data shape), ValueError (bad value).",
             "The line number points at *your* code, not at the library that raised it."],
        steps=["Copy the LAST line, plus the last `File \"...\"` line, into a search.",
               "Run it again with the same input to confirm it is repeatable.",
               "If it is a missing module: `pip install <name>` into the same environment "
               "that runs the script (`python -m pip ...` is the safe form)."],
        arc="paste the traceback into JARVIS and it names the exception class for you.",
    ),
    dict(
        id="py_module_missing",
        keys=[r"modulenotfounderror", r"importerror: no module named",
              r"cannot find module '?[\w@/.-]+", r"err_module_not_found"],
        title="A required module or package is not installed",
        sure="certain",
        means="The program started looking for a library and it is not present in the "
              "environment it is running in. The code is fine; the install is incomplete.",
        why=["The package was never installed, or installed into a different Python.",
             "You are in a virtual environment that does not have it.",
             "The package name differs from the import name (e.g. `pip install Pillow` "
             "gives you `import PIL`)."],
        steps=["`python -m pip install <package>` — the `python -m` form installs into "
               "the interpreter you are actually running.",
             "If you use a venv, activate it in this same terminal first.",
             "For Node: `npm install` inside the project folder, not the parent."],
        arc="say 'system report' to see which Python is running, if you are unsure.",
    ),
    dict(
        id="py_syntax",
        keys=[r"syntaxerror", r"indentationerror", r"unexpected (indent|token|eof)",
              r"expected .{0,20}but got"],
        title="The code will not even parse",
        sure="certain",
        means="This is a shape error, not a logic error — the file never ran. The caret "
              "and line number point at the first place it stopped making sense.",
        why=["Usually the line ABOVE the reported line: an unclosed bracket, quote, or "
             "a missing colon.",
             "Mixed spaces and tabs in Python.",
             "A paste that dropped a line."],
        steps=["Look one line above the reported line, then at the reported line.",
               "Count brackets and quotes on those two lines.",
               "Python: `python -m py_compile file.py` checks without running."],
        arc="nothing automatic — JARVIS will not edit your source to 'fix' a parse error.",
    ),
    dict(
        id="py_permission",
        keys=[r"permissionerror", r"errno 13", r"eacces", r"operation not permitted"],
        title="Permission denied (the program is fine, the folder is not)",
        sure="certain",
        means="Something tried to write where it is not allowed. Very often it is a "
              "system folder, or a file another program has open.",
        why=["Writing into Program Files or a root-owned directory.",
             "The file is open in Excel/Word, which locks it on Windows.",
             "npm/pip run with sudo once, leaving root-owned cache files."],
        steps=["Write to your own folder instead — Desktop or Documents.",
               "Close the program that has the file open.",
               "Only if it is your own cache: fix the owner, do not sudo a package "
               "manager as a habit."],
        arc="nothing — JARVIS writes only new files, in your own folders, by design.",
    ),
    dict(
        id="git",
        keys=[r"fatal: not a git repository", r"permission denied \(publickey\)",
              r"rejected.{0,30}non-fast-forward", r"fatal: refusing to merge unrelated"],
        title="Git refused the operation",
        sure="certain",
        means="Either you are not inside a repository, your SSH key is not accepted, or "
              "the branches have diverged and git will not guess which side wins.",
        why=["`git init` never run, or you are one folder too high.",
             "The SSH key was never added to the remote account.",
             "Someone pushed to the same branch since your last pull."],
        steps=["`git status` first — it says which repository you are in and what is staged.",
               "For publickey: `ssh -T git@github.com` prints the real reason.",
               "For non-fast-forward: `git pull --rebase`, then push again."],
        arc="nothing — JARVIS leaves your repositories alone.",
    ),

    # ---------------- Browser / network ----------------
    dict(
        id="net_dns",
        keys=[r"err_name_not_resolved", r"dns_probe_finished", r"server dns address could not be found",
              r"could not resolve host", r"name or service not known"],
        title="The name could not be turned into an address (DNS)",
        sure="certain",
        means="The internet may be fine; the *lookup* failed. Browsers say "
              "ERR_NAME_NOT_RESOLVED, the command line says 'could not resolve host'.",
        why=["Wi-Fi is on but the router has no DNS — often right after connecting.",
             "A VPN or a manual DNS setting that no longer answers.",
             "The site's domain actually expired or is misspelled."],
        steps=["Turn Wi-Fi off and on, then retry (this re-requests DNS).",
               "Try 1.1.1.1 in the browser by IP path: open https://1.1.1.1 to see if "
               "the network works at all.",
               "Flush the cache: `ipconfig /flushdns` (Windows) or "
               "`sudo resolvectl flush-caches` (Linux)."],
        arc="weather, FX and stock quotes need the network — they will say so, not fail silently.",
    ),
    dict(
        id="net_refused",
        keys=[r"err_connection_refused", r"err_connection_reset", r"connection refused",
              r"err_connection_closed", r"failed to connect to .{0,40}port \d+"],
        title="Something is listening on nothing (connection refused)",
        sure="certain",
        means="The address is right, but nothing accepted the connection on that port. "
              "This is the classic 'my local server is not running' error.",
        why=["The server (dev server, database, Ollama) is not started.",
             "It is running on a different port than the one in the URL or config.",
             "A firewall blocked it — common when binding to 0.0.0.0 vs 127.0.0.1."],
        steps=["Confirm the server is up: it prints its own URL when it starts.",
             "Check the port matches exactly — 3000 vs 3001 is the usual culprit.",
             "On Windows: `netstat -ano | findstr :PORT` shows who, if anyone, holds it."],
        arc="say 'system report' for a live view; JARVIS can check whether a local port answers.",
    ),
    dict(
        id="http_code",
        keys=[r"\b40[134]\b.{0,20}(error|forbidden|not found)", r"error 404", r"error 403",
              r"error 401", r"page not found"],
        title="The server answered, and said no",
        sure="certain",
        means="The network worked. 401 = not signed in, 403 = signed in but not allowed, "
              "404 = that address does not exist on this server.",
        why=["404: a typo, a moved page, or the API path changed version.",
             "403: the account lacks the permission, or a CDN blocked the client.",
             "401: the token expired."],
        steps=["Fix the URL first — 404 is nearly always the path.",
               "Sign out and back in for 401.",
               "For 403 on your own server, check the file/folder permissions it serves."],
        arc="nothing — JARVIS cannot log into your accounts.",
    ),
    dict(
        id="tls",
        keys=[r"net::err_cert", r"your connection is not private", r"certificate (has )?expired",
              r"ssl certificate problem", r"self.signed certificate"],
        title="The certificate does not check out",
        sure="certain",
        means="Your browser could not verify that the site is who it claims to be. "
              "Never click through this one on a bank, mail, or shopping site.",
        why=["The certificate genuinely expired or was misissued.",
             "The device's clock is wrong — a wrong date breaks every certificate.",
             "A company/campus proxy is intercepting traffic."],
        steps=["Check the system date and time first. It is wrong more often than people expect.",
               "If the clock is right and the site is important: do not proceed — close the tab.",
               "If you are on a work network, ask IT whether they inspect TLS."],
        arc="say 'secure phishing' with the URL — it lists the usual impersonation signals.",
    ),
    dict(
        id="offline",
        keys=[r"err_internet_disconnected", r"no internet", r"network is unreachable",
              r"you are offline", r"err_network_changed"],
        title="There is no network path at all",
        sure="certain",
        means="The machine cannot reach anything, not even DNS. Everything local still "
              "works.",
        why=["Wi-Fi is connected to a router with no upstream.",
             "A VPN dropped and took the default route with it.",
             "A captive portal is waiting for you to click 'accept'."],
        steps=["Open any plain http page to see whether a captive portal appears.",
               "Disconnect the VPN and retry.",
               "`ping 1.1.1.1` — if that works but names fail, it is DNS only."],
        arc="everything offline still works: files, media, math, the coach, your library.",
    ),

    # ---------------- Media / documents ----------------
    dict(
        id="ffmpeg",
        keys=[r"moov atom not found", r"invalid data found when processing input",
              r"no such filter", r"error while opening encoder", r"unknown encoder"],
        title="ffmpeg could not read the file",
        sure="certain",
        means="'moov atom not found' means the recording was cut off before its index "
              "was written — typically a phone or camera whose battery died, or a "
              "download that stopped early.",
        why=["The file is truncated or still copying.",
             "The container is fine but the codec is not in this build of ffmpeg.",
             "The file was renamed to .mp4 while actually being something else."],
        steps=["Try to play it once to see if anything is there at all.",
               "Check the real container: ffprobe prints it even for a broken index.",
               "A truncated file can sometimes be recovered, but assume it cannot — and "
               "never overwrite the original."],
        arc="say 'video studio catalog' to see what this build of ffmpeg can actually do.",
    ),
    dict(
        id="file_locked",
        keys=[r"the file is in use", r"being used by another program", r"cannot access the file because it is being used",
              r"file is open in another"],
        title="Another program is holding the file",
        sure="certain",
        means="Windows lets only one program write a file at a time in many cases. "
              "Nothing is corrupt; the file is simply busy.",
        why=["Excel/Word/Photoshop has it open, possibly in a background window.",
             "A sync client (OneDrive, Drive) is uploading it.",
             "An antivirus scanner is mid-scan."],
        steps=["Close the program that owns it — check the taskbar and Alt+Tab.",
               "Wait 30 seconds and retry (sync clients lock briefly).",
               "Copy it to another folder and work on the copy."],
        arc="JARVIS never writes over your original — it always makes a new file.",
    ),
    dict(
        id="pdf_office",
        keys=[r"the file is (corrupt|c damaged)", r"cannot be opened because it is corrupt",
              r"unsupported file format", r"this file is password protected"],
        title="The document could not be parsed",
        sure="likely",
        means="The program believes the file's internal structure is wrong, or it is "
              "encrypted. The bytes exist; the reader refuses them.",
        why=["The download was incomplete (check the size against the source).",
             "It is genuinely password-protected.",
             "It is a different format than the extension claims."],
        steps=["Download it again and compare the file size.",
               "If it needs a password, ask the sender — JARVIS does not crack files.",
               "Try opening it in a browser, which is more forgiving than Office."],
        arc="say 'read' with the path — JARVIS will quote what it can actually extract.",
    ),

    # ---------------- System / hardware ----------------
    dict(
        id="no_audio",
        keys=[r"no (audio )?output device", r"audio device (not found|is disabled)",
              r"no sound.{0,20}(device|output)", r"default playback device"],
        title="No audio output device",
        sure="certain",
        means="Windows sees no working speaker endpoint, so every program is silent "
              "even though nothing failed.",
        why=["Bluetooth headphones are paired but disconnected.",
             "The audio driver was disabled by an update.",
             "The device is set to 'Disabled' in Sound settings."],
        steps=["Click the speaker icon → check the output device chosen.",
               "Settings → System → Sound → 'Manage sound devices' → enable what is off.",
               "Reboot once — this genuinely fixes the driver state most of the time."],
        arc="nothing — no tool can restore a driver that did not load.",
    ),
    dict(
        id="usb_disk",
        keys=[r"disk is write.protected", r"you need to format the disk",
              r"the disk you inserted was not readable", r"device is not ready"],
        title="The USB disk is not readable",
        sure="likely",
        means="Windows can see the device but not its filesystem. It is often the "
              "filesystem, not the data, that is damaged.",
        why=["The drive was unplugged during a write ('eject' exists for a reason).",
             "It is formatted for macOS (APFS) or Linux (ext4) and Windows has no driver.",
             "The physical flash chip is failing."],
        steps=["Do NOT accept 'Format disk' — that dialog erases everything.",
               "Try it on another machine to see whether the data is really gone.",
               "If the files matter: image the drive first, recover from the image."],
        arc="if it mounts at all, say 'scan that drive' and JARVIS indexes the media read-only.",
    ),
]

_COMPILED = [(sig, [re.compile(k, re.I | re.M) for k in sig["keys"]]) for sig in SIGNATURES]

# Lines that look like an error even when no signature matched — used to quote back.
ERRORISH = re.compile(
    r"(error|failed|failure|cannot|could not|unable|denied|refused|not found|invalid|"
    r"exception|traceback|fatal|warning: [a-z]|0x[0-9a-f]{6,8}|stop code|err_)", re.I)

_NEGATIVE = re.compile(r"(no errors?|0 errors|error.?free|errors?: 0)\b", re.I)


# --------------------------------------------------------------------------
def clean(text: str) -> str:
    """Normalise OCR output: collapse the ragged whitespace OCR leaves behind."""
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()[:MAX_CHARS]


def lines_of(text: str) -> list[str]:
    """Split into lines; if OCR gave one long line, split on sentence-ish breaks."""
    text = clean(text)
    if not text:
        return []
    rows = [r.strip(" .|") for r in text.split("\n") if r.strip()]
    if len(rows) <= 2 and len(text) > 120:
        rows = [r.strip(" .|") for r in re.split(r"(?<=[.!?])\s{1,}", text) if r.strip()]
    return rows


def match(text: str) -> list[dict]:
    """All signatures that hit, best first. Empty list = JARVIS does not know this one."""
    text = clean(text)
    if not text:
        return []
    hits = []
    for sig, patterns in _COMPILED:
        hit_keys = [p for p in patterns if p.search(text)]
        if not hit_keys:
            continue
        weight = len(hit_keys) + (0.5 if sig["sure"] == "certain" else 0.0)
        if sig.get("fallback"):
            weight -= 5.0          # only chosen when nothing more specific matched
        hits.append((weight, sig, [p.pattern for p in hit_keys]))
    hits.sort(key=lambda row: (-row[0], SIGNATURES.index(row[1])))
    return [{"sig": sig, "matched": keys, "weight": w} for w, sig, keys in hits]


def quote(text: str, limit: int = MAX_LINES) -> list[str]:
    """The lines worth showing back — the error-looking ones, in screen order."""
    rows = lines_of(text)
    picked = [r for r in rows if ERRORISH.search(r) and not _NEGATIVE.search(r)]
    if not picked:
        picked = rows
    seen: list[str] = []
    for row in picked:
        short = row if len(row) <= 160 else row[:157] + "…"
        if short not in seen:
            seen.append(short)
    return seen[:limit]


def is_error(text: str) -> bool:
    """Whether there is anything worth diagnosing at all."""
    text = clean(text)
    if not text or _NEGATIVE.search(text):
        return False
    if match(text):
        return True
    return bool(ERRORISH.search(text))


def search_hint(text: str) -> str:
    """The exact words to search — built from the screen, not from a guess."""
    rows = quote(text, 2)
    words = " ".join(rows).split()
    phrase = " ".join(words[:10]).replace('"', "").strip()
    return phrase or text.strip()[:80]


def _tanglish(lang_text: str) -> bool:
    low = (lang_text or "").lower()
    return bool(re.search(r"\b(enna|da|machi|pannu|sollu|yen|aaguthu|aagudhu|varudhu|"
                          r"theriyala|epdi|oru|romba|irukku)\b", low))


# --------------------------------------------------------------------------
def explain(text: str = "", screen: bool = False, lang_text: str = "",
            show_sources: bool = True) -> str:
    """The main entry point: text in, a plain-language diagnosis out.

    `text`      what you pasted, or the OCR'd screen
    `screen`    if True and `text` is empty, capture and OCR the screen
    `lang_text` the user's own words, so a Tanglish speaker gets a Tanglish line
    """
    source = "what you gave me"
    if not clean(text) and screen:
        from . import vision
        text = vision.screen_text()
        source = "your screen"
        if text.startswith("ERROR:"):
            return (text + "\n\nSay 'explain this' and paste the error text instead — "
                    "I will diagnose the text exactly the same way.")
        if text.startswith("no readable text"):
            return ("I captured the screen but could not read any text on it. If the "
                    "error is in an image or a game, paste the text to me instead.")

    text = clean(text)
    if not text:
        return ("I have no text to read. Screen: say 'what is this error on my screen'. "
                "Or paste the error message here and I will name it.")

    if _NEGATIVE.search(text):
        return ("There is nothing to diagnose there — the lines I can see explicitly say "
                "there are no errors. I will not invent a problem.")

    quiet = re.search(r"\b(screenshot|photo|picture|camera|selfie|wallpaper|art)\b",
                      text, re.I)
    hits = match(text)
    quoted = quote(text)

    if not hits:
        if quiet and not ERRORISH.search(text):
            return ("I read the text, but this does not look like an error — it reads "
                    f"like {quiet.group(1)} material. Nothing to fix.")
        head = [f"I read {source}, but I do not recognise this error — so I will not "
                f"guess at a cause."]
        if quoted:
            head.append("")
            head.append("What I actually see:")
            head += [f'  "{row}"' for row in quoted[:3]]
        head += ["",
                 f"If you want it looked up, say: search {search_hint(text)}",
                 "Or tell me which program produced it and I will narrow it down."]
        return "\n".join(head)

    best = hits[0]["sig"]
    others = [h["sig"] for h in hits[1:3]]
    out: list[str] = []

    if quoted:
        out.append(f'🔎 I read {source}:')
        out.append(f'   "{quoted[0]}"')
        out.append("")

    out.append(f"**{best['title']}**")
    out.append(f"What it means: {best['means']}")
    out.append("")
    out.append("Why this happens, most likely first:")
    out += [f"  {i}. {why}" for i, why in enumerate(best["why"], 1)]
    out.append("")
    out.append("Do this, in order:")
    out += [f"  {i}. {step}" for i, step in enumerate(best["steps"], 1)]

    if best.get("arc"):
        out += ["", f"JARVIS: {best['arc']}"]

    if others:
        out += ["", "I also see traces of: " + "; ".join(s["title"] for s in others)
                + " — if the first fix does not help, say 'explain this' again with the "
                  "message that remains."]

    if show_sources:
        sure = ("This one is a documented code — the meaning of the digits is fixed."
                if best["sure"] == "certain" else
                "This wording varies between versions, so read the causes as the likely "
                "order, not as certainty.")
        out += ["", f"Confidence: {sure} Your specific machine and files: unknown until "
                    "you try the first step."]

    if _tanglish(lang_text):
        out += ["", f"Machi, mudhal-a step 1 pannunga — {best['title'].split('(')[0].strip()} "
                    "enna-nu theriyum, aana un file-a paakama naan guess panna maaten."]
    return "\n".join(out)


def known() -> int:
    """How many error families this build can actually name."""
    return len(SIGNATURES)


def catalog() -> str:
    """Everything JARVIS can recognise, with its confidence class — for `--all` output."""
    rows = [f"{i:>2}. {sig['title']}  [{sig['sure']}]"
            for i, sig in enumerate(SIGNATURES, 1)]
    return (f"{len(SIGNATURES)} error families:\n" + "\n".join(rows)
            + "\n\nAnything outside this list gets the text back and an honest "
              "'I do not recognise it' — never an invented cause.")


def read_clipboard() -> str:
    """Clipboard text, so 'explain this' works with no arguments at all."""
    try:
        if IS_WIN:
            out = quiet.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True, text=True, timeout=10)
            return out.stdout or ""
        for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"],
                    ["xsel", "-b"], ["pbpaste"]):
            if shutil.which(cmd[0]):
                out = quiet.run(cmd, capture_output=True, text=True, timeout=10)
                return out.stdout or ""
    except Exception:
        return ""
    return ""


def from_clipboard_or_screen(lang_text: str = "") -> str:
    """No arguments: try the clipboard first (exact text), then the screen (OCR)."""
    clip = clean(read_clipboard())
    if clip and is_error(clip):
        return explain(clip, lang_text=lang_text)
    if clip:
        return ("Your clipboard text does not look like an error, so I left it alone. "
                "Say 'what is this error on my screen' to read the screen instead.")
    return explain("", screen=True, lang_text=lang_text)
