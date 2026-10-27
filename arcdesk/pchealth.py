"""Why is this machine slow? — measured, explained, and fixable.

`system_report` shows numbers. This says what the numbers *mean* and what to do about
them, which is a different job and a much easier one to get wrong.

Two rules decide the whole design:

1. **Two samples, one second apart.** A single `cpu_percent()` reading is noise — the
   thing that pegged your CPU may have already finished. Everything here is a *delta*
   over a real interval, and the reply says which interval.
2. **A finding needs evidence.** No rule fires without the measurement that triggered
   it, quoted back: "3.1 of 7.9 GB used by Chrome alone". If a sensor is missing
   (temperature on most Windows laptops, for instance) the reply says it is missing —
   it never reports "cool" because it cannot see.

Nothing here kills a process, changes a setting or writes to the registry. It reads,
converts to a sentence, and hands the decision to you. The one action it *suggests*
(close a named app) is already `confirm=True` elsewhere in ARC.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

GAP = 1.0                       # seconds between the two samples
TOP_N = 6                       # processes named in the reply
RAM_HIGH, RAM_MED = 90.0, 80.0
DISK_LOW_PCT, DISK_LOW_GB = 8.0, 12.0
CPU_HOG = 40.0                  # one process, measured over the gap
CPU_PEGGED = 85.0               # the whole machine
SWAP_HIGH_MB = 1536
PROC_MANY = 260
STARTUP_MANY = 15
TEMP_HOT, TEMP_WARM = 85.0, 78.0
UPTIME_LONG = 21.0


# ------------------------------------------------------------------ sampling
def _psutil():
    try:
        import psutil
        return psutil
    except Exception:
        return None


def _top_processes(ps, first: dict[int, tuple[float, float]], gap: float) -> list[dict]:
    """Per-process CPU over exactly `gap` seconds, plus RSS. Measured, not guessed."""
    rows = []
    for proc in ps.process_iter(["pid", "name", "memory_info"]):
        try:
            pid = proc.info["pid"]
            name = (proc.info["name"] or f"pid {pid}").strip()
            rss = getattr(proc.info["memory_info"], "rss", 0) or 0
            now = proc.cpu_times()
            cpu_now = now.user + now.system
            before = first.get(pid)
            pct = None
            if before is not None:
                pct = max(0.0, (cpu_now - before[1]) / gap * 100.0)
            rows.append({"pid": pid, "name": name, "rss_mb": round(rss / 1048576, 1),
                         "cpu_pct": None if pct is None else round(pct, 1),
                         "cpu_ticks": cpu_now})
        except Exception:
            continue
    return rows


def _disks(ps) -> list[dict]:
    out = []
    skip = {"proc", "sys", "dev", "run", "snap", "boot"}
    for part in ps.disk_partitions(all=False):
        try:
            usage = ps.disk_usage(part.mountpoint)
        except Exception:
            continue
        if usage.total < 256 * 1024 * 1024 and part.mountpoint != "/":
            continue                                   # docker overlays, esps
        if not IS_WIN and part.mountpoint.strip("/").split("/")[0] in skip:
            continue
        free_gb = usage.free / 1073741824
        total_gb = usage.total / 1073741824
        out.append({"mount": part.mountpoint, "fs": part.fstype or "",
                    "total_gb": round(total_gb, 1), "free_gb": round(free_gb, 1),
                    "pct_free": round(free_gb / total_gb * 100, 1) if total_gb else 0.0,
                    "removable": "removable" in (part.opts or "") or
                                 "cdrom" in (part.fstype or "")})
    out.sort(key=lambda d: d["pct_free"])
    return out


def startup_items() -> list[dict] | None:
    """What starts by itself. Read-only. None = this platform cannot be read headlessly."""
    if IS_WIN:
        try:
            import winreg
        except Exception:
            return None
        found: list[dict] = []
        places = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
             "your account"),
            (winreg.HKEY_CURRENT_USER,
             r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "your account"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run",
             "all users"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "all users"),
        ]
        for hive, path, scope in places:
            try:
                with winreg.OpenKey(hive, path) as key:
                    index = 0
                    while True:
                        try:
                            name, value, _kind = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        index += 1
                        found.append({"name": name, "command": str(value)[:120],
                                      "scope": scope})
            except OSError:
                continue
        return found
    if not IS_MAC:
        folder = Path(os.path.expanduser("~/.config/autostart"))
        if not folder.is_dir():
            return []
        found = []
        for entry in sorted(folder.glob("*.desktop"))[:60]:
            label = entry.stem
            try:
                for line in entry.read_text(errors="replace").splitlines():
                    if line.startswith("Name="):
                        label = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
            found.append({"name": label, "command": str(entry), "scope": "your account"})
        return found
    return None


def sample(gap: float = GAP) -> dict:
    """One honest snapshot: two readings `gap` seconds apart, plus the static facts."""
    ps = _psutil()
    if ps is None:
        return {"error": "psutil is not installed, so I have no measurements to show",
                "platform": sys.platform}
    start = time.time()
    ps.cpu_percent(interval=None)                       # prime the counters
    before = {}
    for proc in ps.process_iter(["pid"]):
        try:
            t = proc.cpu_times()
            before[proc.pid] = (time.time(), t.user + t.system)
        except Exception:
            continue
    io_before = None
    try:
        io_before = ps.disk_io_counters()
    except Exception:
        pass
    time.sleep(gap)
    cpu_pct = ps.cpu_percent(interval=None)
    per_core = ps.cpu_percent(interval=None, percpu=True)
    rows = _top_processes(ps, before, gap)
    io_rate = None
    try:
        io_after = ps.disk_io_counters()
        if io_before and io_after:
            dt = max(0.2, time.time() - start)
            io_rate = {
                "read_mbps": round((io_after.read_bytes - io_before.read_bytes) / dt / 1048576, 1),
                "write_mbps": round((io_after.write_bytes - io_before.write_bytes) / dt / 1048576, 1),
            }
    except Exception:
        pass

    mem = ps.virtual_memory()
    swap = ps.swap_memory()
    battery = None
    try:
        bat = ps.sensors_battery()
        if bat is not None:
            battery = {"pct": round(bat.percent, 0), "plugged": bool(bat.power_plugged)}
    except Exception:
        battery = None
    temps = None
    try:
        if hasattr(ps, "sensors_temperatures"):
            raw = ps.sensors_temperatures() or {}
            picked = []
            for label, entries in raw.items():
                for entry in entries:
                    if entry.current:
                        picked.append({"label": entry.label or label,
                                       "current_c": round(float(entry.current), 1)})
            temps = picked[:6] if picked else []
        else:
            temps = []                              # platform has no sensor API at all
    except Exception:
        temps = []
    load = None
    try:
        load = tuple(round(v, 2) for v in os.getloadavg())
    except Exception:
        load = None

    by_cpu = sorted([r for r in rows if r["cpu_pct"] is not None],
                    key=lambda r: -(r["cpu_pct"] or 0))
    by_ram = sorted(rows, key=lambda r: -r["rss_mb"])
    gb = 1073741824
    return {
        "platform": sys.platform,
        "gap_s": gap,
        "taken_at": int(start),
        "cpu_pct": round(cpu_pct, 1),
        "per_core": [round(v, 1) for v in per_core],
        "cpu_count": ps.cpu_count(logical=True),
        "load": load,
        "ram": {"total_gb": round(mem.total / gb, 1), "used_gb": round(mem.used / gb, 1),
                "available_gb": round(mem.available / gb, 1), "pct": round(mem.percent, 1)},
        "swap": {"total_gb": round(swap.total / gb, 1), "used_gb": round(swap.used / gb, 1),
                 "pct": round(swap.percent, 1)},
        "processes": rows,
        "top_cpu": by_cpu[:TOP_N],
        "top_ram": by_ram[:TOP_N],
        "proc_count": len(rows),
        "disks": _disks(ps),
        "io": io_rate,
        "battery": battery,
        "temps": temps,
        "uptime_days": round((time.time() - ps.boot_time()) / 86400, 1),
        "startup": startup_items(),
    }


# ---------------------------------------------------------------- diagnosis
# Each rule gets the sample and returns a finding or None. Pure functions, so the
# test can feed them a synthetic machine instead of waiting for one to be slow.
def _mb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def rule_ram(s: dict) -> dict | None:
    ram = s.get("ram") or {}
    pct = ram.get("pct") or 0
    if pct < RAM_MED:
        return None
    hogs = [p for p in (s.get("top_ram") or []) if p["rss_mb"] >= 120][:3]
    fixes = []
    if hogs:
        fixes.append(f"Close {hogs[0]['name']} when you are done with it — it alone holds "
                     f"{_mb(hogs[0]['rss_mb'])}. JARVIS will not kill it for you: say "
                     f"'close {hogs[0]['name'].split('.')[0].lower()}' and it asks first.")
    fixes += ["Check what is running in the tray — chat apps and browsers with 30 tabs are "
              "the usual pair.",
              "Reboot. It is unglamorous and it clears what leaks."]
    biggest = (f" — biggest single app: {hogs[0]['name']} at {_mb(hogs[0]['rss_mb'])}"
               if hogs else "")
    return {
        "id": "ram", "severity": "high" if pct >= RAM_HIGH else "medium",
        "title": "Memory is nearly full — that is the slow",
        "metric": f"{ram.get('used_gb')} of {ram.get('total_gb')} GB used ({pct:.0f}%), "
                  f"{ram.get('available_gb')} GB left{biggest}",
        "why": "When Windows runs out of RAM it starts shuffling memory to disk. Every "
               "click then waits for the disk, which is why 'the whole PC' feels slow "
               "rather than one app.",
        "fixes": fixes,
        "arc": "say 'system report' for the live view of the same numbers.",
    }


def rule_swap(s: dict) -> dict | None:
    swap = s.get("swap") or {}
    used_mb = (swap.get("used_gb") or 0) * 1024
    if used_mb < SWAP_HIGH_MB:
        return None
    return {
        "id": "swap", "severity": "high",
        "title": "The machine is paging to disk (swap in heavy use)",
        "metric": f"{swap.get('used_gb')} GB of {swap.get('total_gb')} GB swap/pagefile in use",
        "why": "Anything in swap is not in RAM any more, so opening it again costs a disk "
               "read. This is the second half of a memory problem, and the part that makes "
               "switching windows feel sticky.",
        "fixes": ["Close the largest app and watch this number in 'system report'.",
                  "If this happens daily with 8 GB of RAM, adding RAM is the only real fix; "
                  "a bigger pagefile just makes it slower, not faster.",
                  "Turn off 'fast startup' only if you hibernate a lot — otherwise ignore it."],
        "arc": "the number above is measured now; it is not an estimate.",
    }


def rule_cpu(s: dict) -> dict | None:
    pct = s.get("cpu_pct") or 0
    hot = [p for p in (s.get("top_cpu") or []) if (p.get("cpu_pct") or 0) >= CPU_HOG][:3]
    if pct < CPU_PEGGED and not hot:
        return None
    if hot:
        who = ", ".join(f"{p['name']} at {p['cpu_pct']:.0f}%" for p in hot)
        return {
            "id": "cpu_process", "severity": "high" if pct >= CPU_PEGGED else "medium",
            "title": "One process is using the CPU",
            "metric": f"{who} — measured over {s.get('gap_s', GAP):.1f} s; "
                      f"whole machine at {pct:.0f}% of {s.get('cpu_count')} threads",
            "why": "A single busy process starves everything else of CPU time, so every "
                   "other app looks slow while the busy one looks busy.",
            "fixes": [f"If you did not start {hot[0]['name']}, close it and check it is "
                      f"something you meant to install.",
                      "Antivirus scans, Windows Update and file indexing all do this for a "
                      "few minutes and then stop — wait and re-check before changing anything.",
                      "If it is a language model or a video render, it is doing what you "
                      "asked; move on and let it finish."],
            "arc": "say 'system report' to watch it live for 10 seconds.",
        }
    return {
        "id": "cpu_all", "severity": "high",
        "title": "The CPU is pegged across the board",
        "metric": f"{pct:.0f}% over {s.get('gap_s', GAP):.1f} s across "
                  f"{s.get('cpu_count')} threads; load {s.get('load')}",
        "why": "No single process dominates, which usually means several things are working "
               "at once — a batch of updates, an antivirus scan, or a background sync.",
        "fixes": ["Wait five minutes and re-check; if it drops, it was housekeeping.",
                  "Look for a cloud-sync client uploading — that shows in disk writes too.",
                  "If it never drops, reboot and re-measure before changing any setting."],
        "arc": "this is measured, not guessed: two samples, one second apart.",
    }


def rule_disk(s: dict) -> dict | None:
    disks = s.get("disks") or []
    tight = [d for d in disks if not d.get("removable") and
             (d.get("pct_free", 100) <= DISK_LOW_PCT or d.get("free_gb", 999) <= DISK_LOW_GB)]
    if not tight:
        return None
    d = tight[0]
    return {
        "id": "disk_full", "severity": "high",
        "title": "A drive is nearly full",
        "metric": f"{d['mount']} has {d['free_gb']} GB free of {d['total_gb']} GB "
                  f"({d['pct_free']}%)",
        "why": "Windows needs free space for the pagefile, temp files and updates. Under "
               "about 10% free, writes start failing and the whole system slows down "
               "before it ever says 'disk full'.",
        "fixes": ["Settings → System → Storage → Temporary files removes caches, not your files.",
                  "Empty the Recycle Bin.",
                  "Look for a large .iso, .zip or video you have finished with — JARVIS will "
                  "tell you the biggest files, it will not delete them."],
        "arc": "say 'scan my external disk' to see whether a drive has room for the overflow.",
    }


def rule_io(s: dict) -> dict | None:
    io = s.get("io") or {}
    total = (io.get("read_mbps") or 0) + (io.get("write_mbps") or 0)
    if total < 40:
        return None
    return {
        "id": "io", "severity": "medium",
        "title": "Something is moving a lot of data to or from the disk",
        "metric": f"{io.get('read_mbps')} MB/s read · {io.get('write_mbps')} MB/s write "
                  f"over {s.get('gap_s', GAP):.1f} s",
        "why": "At this rate the disk is saturated, so every other program waits its turn. "
               "This is also what makes a laptop feel hot and loud.",
        "fixes": ["Check for a sync client (OneDrive, Drive, Dropbox) uploading in the tray.",
                  "Check for a game or Windows Update downloading.",
                  "A big file copy does this on purpose — it will end."],
        "arc": "nothing to change; this is information, not a fault.",
    }


def rule_startup(s: dict) -> dict | None:
    items = s.get("startup")
    if items is None or len(items) < STARTUP_MANY:
        return None
    names = ", ".join(i["name"] for i in items[:6])
    return {
        "id": "startup", "severity": "medium",
        "title": "A lot starts by itself at login",
        "metric": f"{len(items)} startup entries — {names}"
                  + ("…" if len(items) > 6 else ""),
        "why": "Each one costs boot time and RAM all day, even when you never open it. "
               "This is the single most common reason a laptop got slower over a year "
               "without anyone changing anything.",
        "fixes": ["Task Manager → Startup apps → disable what you do not need at login "
                  "(it stays installed; only the auto-start is turned off).",
                  "Do not disable anything with 'Security', 'Audio', 'Touchpad', 'Graphics' "
                  "or your laptop maker's name in it.",
                  "Say 'startup items' and JARVIS lists them all with their full commands."],
        "arc": "this list was read from the registry, read-only — nothing was changed.",
    }


def rule_procs(s: dict) -> dict | None:
    count = s.get("proc_count") or 0
    if count < PROC_MANY:
        return None
    return {
        "id": "procs", "severity": "note",
        "title": "There are a lot of processes running",
        "metric": f"{count} processes right now",
        "why": "By itself this is normal on a modern machine — browsers and Electron apps "
               "each spawn a dozen. It only matters together with high RAM or CPU, which "
               "would have been reported above.",
        "fixes": ["Nothing, if memory and CPU are fine.",
                  "If both are high, close whole apps rather than individual processes."],
        "arc": "reported so you are not surprised by the number, not because it is a fault.",
    }


def rule_battery(s: dict) -> dict | None:
    bat = s.get("battery")
    if not bat or bat.get("plugged") or (bat.get("pct") or 100) > 25:
        return None
    return {
        "id": "battery", "severity": "medium",
        "title": "On battery and low — and working hard",
        "metric": f"{bat['pct']:.0f}% on battery, CPU at {s.get('cpu_pct')}%",
        "why": "Laptops deliberately slow the CPU when the battery is low, so everything "
               "feels sluggish at exactly the wrong moment.",
        "fixes": ["Plug in.", "If you must stay unplugged: Settings → Power → Battery saver, "
                             "and close the heavy app."],
        "arc": "measured from the battery sensor, not from a timer.",
    }


def rule_temp(s: dict) -> dict | None:
    temps = s.get("temps")
    if not temps:
        return None
    hottest = max(temps, key=lambda t: t["current_c"])
    if hottest["current_c"] < TEMP_WARM:
        return None
    return {
        "id": "temp", "severity": "high" if hottest["current_c"] >= TEMP_HOT else "medium",
        "title": "It is running hot, and it is slowing itself down on purpose",
        "metric": f"{hottest['label']} at {hottest['current_c']} °C",
        "why": "Above about 85 °C a CPU throttles to protect itself. Performance drops "
               "before you ever see a warning, which people experience as 'it got slow "
               "for no reason'.",
        "fixes": ["Check the fan is actually spinning and not blocked — a laptop on a bed "
                  "is the classic case.",
                  "Compressed air on the vents, once, properly.",
                  "If it is 3+ years old on a desk, thermal paste is the real fix — a "
                  "repair shop job, not a software one."],
        "arc": "this sensor is the one your machine exposes; some laptops expose none.",
    }


def rule_uptime(s: dict) -> dict | None:
    days = s.get("uptime_days") or 0
    if days < UPTIME_LONG:
        return None
    return {
        "id": "uptime", "severity": "note",
        "title": "This machine has been up a long time",
        "metric": f"{days:.0f} days without a restart",
        "why": "Long uptimes accumulate leaked memory and half-finished updates. This is a "
               "heuristic, not a measurement — plenty of machines run for months happily.",
        "fixes": ["Restart once, and note whether it feels different. If it does, that is "
                  "your answer; if it does not, ignore this note."],
        "arc": "labelled a heuristic because that is what it is.",
    }


RULES = (rule_ram, rule_swap, rule_cpu, rule_disk, rule_io, rule_startup, rule_procs,
         rule_battery, rule_temp, rule_uptime)
_RANK = {"high": 0, "medium": 1, "note": 2}


def diagnose(s: dict) -> list[dict]:
    """Every rule that has evidence. Sorted so the biggest cause is read first."""
    findings = []
    for rule in RULES:
        try:
            found = rule(s)
        except Exception:
            continue
        if found:
            findings.append(found)
    findings.sort(key=lambda f: (_RANK.get(f["severity"], 3), f["id"]))
    return findings


# ------------------------------------------------------------------ replies
def _verdict(s: dict, findings: list[dict]) -> str:
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    if high:
        return (f"Found {len(high)} thing(s) actually slowing this PC"
                + (f", plus {len(medium)} smaller one(s)" if medium else "") + ".")
    if medium:
        return (f"Nothing serious: {len(medium)} thing(s) worth tidying, none of them "
                f"critical.")
    return ("Nothing here is slowing this machine — memory, CPU and disk all have room.")


def _limits(s: dict) -> list[str]:
    lines = []
    temps = s.get("temps")
    if temps == []:
        lines.append("temperature: this machine exposes no sensor to software, so I did not "
                     "measure heat at all (not 'it is cool' — 'I cannot see it').")
    startup = s.get("startup")
    if startup is None:
        lines.append("startup items: not readable on this platform from here.")
    if s.get("battery") is None:
        lines.append("battery: no battery sensor (desktop, or none exposed).")
    if s.get("io") is None:
        lines.append("disk throughput: counters unavailable, so no MB/s claim is made.")
    if s.get("platform") == "win32":
        lines.append("I read this machine only. No setting, service or registry value was "
                     "changed, and nothing was sent anywhere.")
    return lines


def explain(s: dict | None = None, startup_only: bool = False, lang_text: str = "") -> str:
    """The reply. `s` can be injected by a test; otherwise it is sampled live."""
    if s is None:
        s = sample()
    if s.get("error"):
        return (f"{s['error']}.\n"
                "I will not invent numbers. Install it once — `python -m pip install psutil` "
                "— and ask again; every number after that is measured on this machine.")
    if startup_only:
        return startup_text(s)

    findings = diagnose(s)
    ram = s.get("ram") or {}
    out = [f"**{_verdict(s, findings)}**", ""]
    out.append(f"Measured over {s.get('gap_s', GAP):.1f} s just now: "
               f"CPU {s.get('cpu_pct')}% of {s.get('cpu_count')} threads · "
               f"RAM {ram.get('used_gb')}/{ram.get('total_gb')} GB ({ram.get('pct')}%) · "
               f"free disk "
               + (f"{s['disks'][0]['free_gb']} GB on {s['disks'][0]['mount']}"
                  if s.get("disks") else "unknown")
               + f" · up {s.get('uptime_days')} days")

    if not findings:
        out += ["", "For reference, the biggest memory users right now:"]
        for p in (s.get("top_ram") or [])[:3]:
            out.append(f"  · {p['name']} — {_mb(p['rss_mb'])}")
        out += ["", "If it *feels* slow while these numbers look fine, the bottleneck is "
                    "probably the thing I cannot measure: a single-core app, a slow "
                    "website, or a spinning hard disk. Say 'system report' while it is "
                    "happening and I will look at the moment, not at now."]
        limits = _limits(s)
        if limits:
            out += ["", "What I could not see:"] + [f"  · {line}" for line in limits]
        return "\n".join(out)

    for i, f in enumerate(findings, 1):
        out += ["", f"{i}. **{f['title']}**  ({f['severity']})",
                f"   measured: {f['metric']}",
                f"   why it matters: {f['why']}",
                "   do this:"]
        out += [f"     - {step}" for step in f["fixes"]]
        if f.get("arc"):
            out.append(f"   JARVIS: {f['arc']}")

    out += ["", "One at a time, please: change the top item, wait a minute, and ask again "
                "so the next answer is measured on the new state rather than guessed."]
    limits = _limits(s)
    if limits:
        out += ["", "What I could not see:"] + [f"  · {line}" for line in limits]
    if _tanglish(lang_text):
        top = findings[0]
        out += ["", f"Machi, mudhalla idhu: {top['title'].lower()} — {top['metric']}. "
                    f"Adhu mudinjadhum thirumba 'yen slow' nu kelu, naan pudhu measurement "
                    f"eduppen. Guess panna maaten."]
    return "\n".join(out)


def startup_text(s: dict | None = None) -> str:
    """Every startup entry, read-only, with a caution about what not to disable."""
    if s is None:
        s = sample(GAP)
    if s.get("error"):
        return s["error"]
    items = s.get("startup")
    if items is None:
        return ("I cannot read the startup list on this platform from here. On Windows it "
                "is the HKCU/HKLM 'Run' keys; JARVIS reads them and nothing else.")
    if not items:
        return ("Nothing starts automatically at login — the Run keys are empty and there "
                "is no autostart folder. Nothing to tidy.")
    out = [f"{len(items)} startup entr(ies), read read-only from the registry:",
           "  (name — scope)"]
    for item in items:
        out.append(f"  · {item['name']}  — {item['scope']}")
    out += ["",
            "Turn them off in Task Manager → Startup apps. That stops the auto-start only;",
            "the program stays installed and still opens when you click it.",
            "",
            "Do not disable anything with Security, Audio, Touchpad, Graphics, or your",
            "laptop maker's name in it. JARVIS changed nothing here."]
    return "\n".join(out)


def _tanglish(text: str) -> bool:
    low = (text or "").lower()
    return bool(re_lang(low))


def re_lang(low: str):
    import re
    return re.search(r"\b(enna|da|machi|pannu|sollu|yen|aaguthu|aagudhu|varudhu|"
                     r"theriyala|epdi|romba|irukku|slow|speed)\b", low)


def quick(s: dict | None = None) -> str:
    """Three lines for the tray / a one-liner question."""
    if s is None:
        s = sample(0.4)
    if s.get("error"):
        return s["error"]
    ram = s.get("ram") or {}
    findings = diagnose(s)
    head = "fine" if not findings else findings[0]["title"]
    return (f"CPU {s.get('cpu_pct')}% · RAM {ram.get('pct')}% · "
            f"disk {s['disks'][0]['pct_free'] if s.get('disks') else '?'}% free · {head}")


def catalog() -> str:
    """The rules, so nobody has to guess what is checked."""
    names = ["RAM pressure", "pagefile/swap thrash", "one CPU-hungry process",
             "whole-CPU load", "nearly-full drive", "disk throughput saturation",
             "startup bloat", "process count", "battery + load", "thermal throttling",
             "long uptime (heuristic)"]
    return (f"{len(names)} checks, every one fired only by a measurement:\n"
            + "\n".join(f"  {i}. {n}" for i, n in enumerate(names, 1))
            + "\n\nEach finding quotes the number that triggered it. Nothing is killed, "
              "no setting is changed.")
