"""Why is it slow? — the rules are tested against synthetic machines.

Waiting for a real laptop to be slow is not a test strategy. So `sample()` collects
measurements and `diagnose()` is a set of pure functions over them: this file feeds it
a machine with 96% RAM, a machine with one CPU hog, a machine with 2% disk free, a hot
machine, a healthy machine — and checks that the reply names the right cause with the
right number.

The honesty checks matter more than the rules:

  * no sensor = "I cannot see it", never "it is fine";
  * no psutil = no numbers invented;
  * a healthy machine gets a clean verdict instead of a list of maybes;
  * nothing is ever killed or changed, and the reply says so.

Run:  python tests/test_pchealth.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import pchealth  # noqa: E402
from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.lite import respond  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<60} {str(got)[:36]!r}")
    ok &= bool(good)


def machine(**over) -> dict:
    """A healthy 2-core laptop, 16 GB, a third of the disk free, cool and plugged in."""
    base = {
        "platform": "win32", "gap_s": 1.0, "taken_at": int(time.time()),
        "cpu_pct": 12.0, "per_core": [14.0, 10.0], "cpu_count": 8, "load": (0.4, 0.5, 0.6),
        "ram": {"total_gb": 16.0, "used_gb": 5.4, "available_gb": 10.6, "pct": 34.0},
        "swap": {"total_gb": 4.0, "used_gb": 0.1, "pct": 3.0},
        "processes": [], "top_cpu": [{"pid": 1, "name": "Code.exe", "rss_mb": 620.0,
                                      "cpu_pct": 6.0}],
        "top_ram": [{"pid": 1, "name": "chrome.exe", "rss_mb": 820.0, "cpu_pct": 4.0},
                    {"pid": 2, "name": "Code.exe", "rss_mb": 620.0, "cpu_pct": 6.0}],
        "proc_count": 180,
        "disks": [{"mount": "C:\\", "fs": "NTFS", "total_gb": 476.0, "free_gb": 160.0,
                   "pct_free": 33.6, "removable": False}],
        "io": {"read_mbps": 1.2, "write_mbps": 0.8},
        "battery": {"pct": 88.0, "plugged": True},
        "temps": [{"label": "CPU", "current_c": 54.0}],
        "uptime_days": 1.2,
        "startup": [{"name": "OneDrive", "command": "onedrive.exe", "scope": "your account"}],
    }
    base.update(over)
    return base


def ids(s: dict) -> list[str]:
    return [f["id"] for f in pchealth.diagnose(s)]


print("1) a healthy machine gets a clean verdict, not a list of maybes")
healthy = machine()
check("no findings at all", ids(healthy), [])
said = pchealth.explain(healthy)
check("says nothing is slowing it", "Nothing here is slowing" in said, True)
check("still shows the real numbers", "CPU 12.0%" in said and "5.4/16.0 GB" in said, True)
check("and admits what it cannot measure", "cannot measure" in said or "could not see" in said,
      True)

print("2) RAM pressure, with the app named and the number quoted")
rammy = machine(ram={"total_gb": 8.0, "used_gb": 7.7, "available_gb": 0.3, "pct": 96.0},
                top_ram=[{"pid": 1, "name": "chrome.exe", "rss_mb": 3100.0, "cpu_pct": 9.0},
                         {"pid": 2, "name": "Photoshop.exe", "rss_mb": 1400.0,
                          "cpu_pct": 3.0}])
found = pchealth.diagnose(rammy)
check("RAM is the first finding", found[0]["id"], "ram")
check("severity is high", found[0]["severity"], "high")
check("the app is named", "chrome.exe" in found[0]["metric"], True)
check("the size is quoted", "3.0 GB" in found[0]["metric"], True)
check("it says ARC will not kill it", "will not kill" in found[0]["fixes"][0], True)
said = pchealth.explain(rammy)
check("the reply leads with the cause", "Memory is nearly full" in said, True)
check("the reply gives ordered steps", "do this:" in said, True)
check("the reply says change one thing, then re-measure",
      "One at a time" in said, True)

print("3) paging is reported separately — it is what makes clicks sticky")
swappy = machine(swap={"total_gb": 8.0, "used_gb": 3.4, "pct": 42.0})
check("swap is flagged", "swap" in ids(swappy), True)
check("with the amount measured",
      "3.4 GB of 8.0 GB" in pchealth.diagnose(swappy)[0]["metric"], True)

print("4) one CPU hog beats a vague 'the CPU is busy'")
hot = machine(cpu_pct=94.0, top_cpu=[{"pid": 9, "name": "MsMpEng.exe", "rss_mb": 210.0,
                                      "cpu_pct": 78.0}])
found = pchealth.diagnose(hot)
check("the process rule fires", found[0]["id"], "cpu_process")
check("the process and its share are named",
      "MsMpEng.exe at 78%" in found[0]["metric"], True)
check("it says the measurement window", "over 1.0 s" in found[0]["metric"], True)
check("the advice includes waiting, because antivirus stops on its own",
      any("Antivirus" in f or "Windows Update" in f for f in found[0]["fixes"]), True)

print("5) a full drive is a cause, not a footnote")
full = machine(disks=[{"mount": "C:\\", "fs": "NTFS", "total_gb": 237.0, "free_gb": 6.1,
                       "pct_free": 2.6, "removable": False}])
found = pchealth.diagnose(full)
check("disk is flagged", found[0]["id"], "disk_full")
check("the free space is quoted", "6.1 GB free of 237.0 GB" in found[0]["metric"], True)
check("it warns that failures start before 'disk full'",
      "before it ever says" in found[0]["why"], True)

print("6) heat — and the honest case where there is no sensor")
warm = machine(temps=[{"label": "Package id 0", "current_c": 91.5}])
found = pchealth.diagnose(warm)
check("thermal throttling is flagged", found[0]["id"], "temp")
check("the reading is quoted", "91.5 °C" in found[0]["metric"], True)
check("it explains throttling, not 'it feels hot'", "throttles" in found[0]["why"], True)
blind = machine(temps=[])
check("no sensor = no finding", "temp" in ids(blind), False)
check("and the reply says it cannot see, not that it is cool",
      "I cannot see it" in pchealth.explain(blind), True)

print("7) startup bloat, and the list that must not be touched")
bloated = machine(startup=[{"name": f"App{i}", "command": f"c:\\app{i}.exe",
                            "scope": "your account"} for i in range(19)])
found = pchealth.diagnose(bloated)
check("startup bloat is flagged", found[0]["id"], "startup")
check("the count is quoted", "19 startup entries" in found[0]["metric"], True)
check("it warns what not to disable",
      any("Security" in f and "Audio" in f for f in found[0]["fixes"]), True)
listing = pchealth.startup_text(bloated)
check("the full list is available", "19 startup entr" in listing, True)
check("and it says nothing was changed", "changed nothing" in listing, True)

print("8) smaller signals are graded correctly")
busy_io = machine(io={"read_mbps": 60.0, "write_mbps": 40.0})
check("heavy disk I/O is a note, not a fault", pchealth.diagnose(busy_io)[0]["severity"],
      "medium")
many = machine(proc_count=310)
check("process count alone is only a note", pchealth.diagnose(many)[0]["severity"], "note")
lowbat = machine(battery={"pct": 11.0, "plugged": False}, cpu_pct=70.0)
check("low battery + load is flagged", "battery" in ids(lowbat), True)
old = machine(uptime_days=34.0)
found = pchealth.diagnose(old)
check("long uptime is honestly called a heuristic",
      "heuristic" in found[0]["why"].lower(), True)

print("9) ordering puts the biggest cause first")
everything = machine(cpu_pct=97.0, ram={"total_gb": 8.0, "used_gb": 7.8,
                                        "available_gb": 0.2, "pct": 97.0},
                     swap={"total_gb": 8.0, "used_gb": 5.0, "pct": 62.0},
                     disks=[{"mount": "C:\\", "fs": "NTFS", "total_gb": 237.0,
                             "free_gb": 3.0, "pct_free": 1.3, "removable": False}],
                     top_cpu=[{"pid": 3, "name": "render.exe", "rss_mb": 900.0,
                               "cpu_pct": 82.0}],
                     temps=[{"label": "CPU", "current_c": 95.0}],
                     proc_count=400, io={"read_mbps": 90.0, "write_mbps": 30.0})
found = pchealth.diagnose(everything)
check("several causes found", len(found) >= 5, True)
check("all high-severity ones come first",
      [f["severity"] for f in found] == sorted([f["severity"] for f in found],
                                               key=lambda v: {"high": 0, "medium": 1,
                                                              "note": 2}[v]), True)
check("the highest-severity count is stated", "actually slowing" in
      pchealth.explain(everything), True)

print("10) no measurements = no invented measurements")
check("missing psutil says so",
      "psutil" in pchealth.explain({"error": "psutil is not installed, so I have no "
                                             "measurements to show"}), True)
check("it refuses to guess anyway",
      "will not invent numbers" in pchealth.explain(
          {"error": "psutil is not installed, so I have no measurements to show"}), True)

print("11) a real sample from this machine, measured")
live = pchealth.sample(0.5)
check("a sample came back", bool(live) and not live.get("error"), True)
check("it really waited",
      live["taken_at"] > 0 and live.get("gap_s") == 0.5, True)
check("CPU is a number in range", isinstance(live.get("cpu_pct"), float)
      and 0 <= live["cpu_pct"] <= 100 * (live.get("cpu_count") or 1), True)
check("disks are listed", isinstance(live.get("disks"), list), True)
check("processes are listed with memory",
      all("rss_mb" in p for p in (live.get("top_ram") or [])), True)
check("the per-process CPU was measured, not assumed",
      all(p["cpu_pct"] is not None for p in (live.get("top_cpu") or [])), True)
check("a quick line exists", "RAM" in pchealth.quick(live), True)

print("12) wired: tool, router, and the words people use")
check("pc_health is registered", "pc_health" in tools.TOOLS, True)
check("tool count", len(tools.TOOLS) >= 84, True)
check("the checks list is honest about the count",
      f"{len(pchealth.RULES) + 1} checks" in tools.call("pc_health", {"action": "checks"}),
      True)
check("the quick action answers", "CPU" in tools.call("pc_health", {"action": "quick"}), True)
for phrase in ("why is my laptop slow", "why is my pc slow", "machi yen slow da",
               "computer romba slow", "my laptop is heating up", "the fan is loud",
               "yen slow aaguthu"):
    _, calls = respond(phrase)
    check(f"“{phrase}” asks pc_health",
          calls and calls[0]["function"]["name"] == "pc_health", True)
for phrase, want in (("system report", "system_report"),
                     ("what's using my ram", "running_apps"),
                     ("why is this not working", "explain"),
                     ("index my documents", "search_inside"),
                     ("play ilaya nila", "play")):
    _, calls = respond(phrase)
    check(f"“{phrase}” still routes to {want}",
          calls[0]["function"]["name"] if calls else None, want)

print("13) a Tanglish speaker gets a Tanglish closing line, still refusing to guess")
tangled = pchealth.explain(rammy, lang_text="machi yen slow da")
check("closes in Tanglish", "Machi" in tangled, True)
check("and still refuses to guess", "Guess panna maaten" in tangled, True)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
