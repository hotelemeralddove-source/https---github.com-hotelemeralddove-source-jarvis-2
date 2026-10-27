"""One JARVIS, one folder — and the screen that explains itself.

Two reports, one round:

  * "multiple files lan ilama ... orey folder ah irukanum ... vera vera files, places la
    irukurathu nala confuse aaguthu" — so `tools/one_place.py` must find every copy, say
    which one is real, and (only with --apply) keep one and park the rest;
  * "magic begin section la ena nadakuthu nay enakku puriyala" — so the magic screen must
    name its six strands, explain each one in a sentence, and have a click target that is
    the same rectangle you can see.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_one_place.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


from tools import one_place as op  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def make_copy(base: Path, version: str = "1.0.0", venv: bool = False,
              age: float = 0.0) -> Path:
    """A folder that looks exactly like an app to the finder."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "run.py").write_text("# launcher\n", encoding="utf-8")
    (base / "requirements.txt").write_text("PySide6\n", encoding="utf-8")
    (base / "arcdesk").mkdir(exist_ok=True)
    (base / "arcdesk" / "__init__.py").write_text(f'__version__ = "{version}"\n',
                                                  encoding="utf-8")
    if venv:
        v = base / ".venv" / "Scripts"
        v.mkdir(parents=True, exist_ok=True)
        (v / "python.exe").write_bytes(b"")
    if age:                       # age in seconds: older files get an older mtime
        import time as _t
        stamp = _t.time() - age
        for f in ("run.py", "requirements.txt"):
            os.utime(base / f, (stamp, stamp))
    return base


print("1. what counts as a copy")
home = Path(tempfile.mkdtemp(prefix="arcdesk-home-"))
good = make_copy(home / "Downloads" / "JARVIS" / "arcdesk-src", "9.0.0", venv=True)
pack = home / "Downloads" / "arcdesk-fix42-launcher-opens"
pack.mkdir(parents=True, exist_ok=True)
(pack / "FIXPACK.txt").write_text("KIND=fixpack\nNAME=fix42\n", encoding="utf-8")
(pack / "JARVIS.bat").write_text("@echo off\r\n", encoding="utf-8")
(home / "Downloads" / "holiday-photos").mkdir(parents=True, exist_ok=True)
check("run.py + requirements.txt is a copy", op.is_copy(good), True)
check("a fix pack folder (no run.py) is not", op.is_copy(home / "Downloads" /
                                                        "arcdesk-fix42-launcher-opens"), False)
check("an ordinary folder is not", op.is_copy(home / "Downloads" / "holiday-photos"), False)
check("the version is read without importing anything", op.version_of(good), "9.0.0")
check("a working environment is noticed", op.has_venv(good), True)

print("\n2. find them all, in the places people actually use")
found = op.find_copies(home, include_self=False)
check("the deep copy is found (Downloads/JARVIS/arcdesk-src)",
      str(good.resolve()) in [str(p.resolve()) for p in found], True)
check("the fix pack is NOT offered as an app",
      any("fix42" in str(p) for p in found), False)
check("each copy appears once", len(found), len({str(p.resolve()) for p in found}))

print("\n3. which one wins")
older = make_copy(home / "Desktop" / "JARVIS-old", "1.0.0", venv=False, age=9000)
copies = op.find_copies(home, include_self=False)
keep = op.choose(copies, home)
check("the copy with a working .venv wins", keep.resolve(), good.resolve())
check("…not the stale one on the Desktop", keep.resolve() == older.resolve(), False)

target = make_copy(home / "JARVIS", "9.1.0", venv=True)
copies = op.find_copies(home, include_self=False)
keep = op.choose(copies, home)
check("a copy already at ~/JARVIS is kept as it is", keep.resolve(), target.resolve())

print("\n4. the plan says what would happen (and changes nothing)")
the_plan = op.plan(copies, keep, home)
check("nothing needs moving", the_plan["move_to_target"], False)
check("the other two would be parked", len(the_plan["park"]), 2)
check("…into JARVIS-OLD", all("JARVIS-OLD" in row["to"] for row in the_plan["park"]),
      True)
check("planning did not touch the disk", (home / "JARVIS-OLD").exists(), False)

print("\n5. --apply keeps one, parks the rest, deletes nothing")
got = op.apply_plan(the_plan)
check("it reports work done", len(got["done"]), 2)
check("nothing failed", got["failed"], [])
check("the kept copy is still there",
      (home / "JARVIS" / "run.py").exists(), True)
check("the Downloads copy was MOVED, not deleted",
      (home / "Downloads" / "JARVIS" / "arcdesk-src").exists(), False)
parked = [p for p in (home / "JARVIS-OLD").glob("*") if p.is_dir()]
check("both parked folders are in JARVIS-OLD", len(parked), 2)
check("…and they still contain the app",
      all((p / "run.py").exists() for p in parked), True)
check("afterwards there is exactly one copy to find",
      len(op.find_copies(home, include_self=False)), 1)

print("\n5b. the tool refuses to move the copy it is running from")
the_plan2 = {"keep": str(op.ROOT), "move_to_target": True,
             "target": str(home / "JARVIS2"), "park": []}
got2 = op.apply_plan(the_plan2)
check("it says no, and says why", got2["done"], [])
check("…naming the reason", "running the tool from" in got2["failed"][0]["why"], True)
check("…and the folder is still where it was", op.ROOT.exists(), True)

print("\n6. --undo puts them back")
op.undo(home)
check("the parked copy is back under Downloads",
      (home / "Downloads" / "JARVIS" / "arcdesk-src" / "run.py").exists(), True)
check("…both of them", (home / "Desktop" / "JARVIS-old" / "run.py").exists(), True)
check("the manifest is cleared afterwards",
      (home / "JARVIS-OLD" / ".moved.json").exists(), False)

print("\n7. the report reads like a person wrote it")
text = op.report(op.find_copies(home, include_self=False),
                 op.choose(op.find_copies(home, include_self=False), home), home)
check("it counts the copies", "copy(ies) of JARVIS found" in text)
check("it names the winner", "<-- keep this one" in text)
check("it ends with ONE thing to double-click", "JARVIS.bat" in text)
tagged = op.report(op.find_copies(home, include_self=False), None, home,
                   op.find_copies(home, include_self=False)[0])
check("…and marks the copy that is running right now", "RUNNING NOW" in tagged, True)
check("it says what it would do, in words", "python tools/one_place.py --apply" in text)

empty = Path(tempfile.mkdtemp(prefix="arcdesk-empty-"))
check("with nothing installed it says what to unzip",
      "unzip ArcDesk-full-project.zip" in op.report([], None, empty))

print("\n7b. scratch folders are not 'my JARVIS'")
# a home that is NOT itself inside a temp folder, so the temp rule can be tested honestly
import tempfile as _tf                                                    # noqa: E402
real_home2 = Path(_tf.mkdtemp(prefix="arcdesk-realhome-", dir=str(Path.home())))
scratch = Path(_tf.mkdtemp(prefix="arc-update-")) / "project"
make_copy(scratch, "1.0.0")
make_copy(real_home2 / "JARVIS", "1.0.0")
try:
    check("a copy inside a temp folder is recognised as temporary",
          op.is_temp(scratch, real_home2), True)
    found2 = op.find_copies(real_home2, include_self=False)
    check("…and never reported as one of your copies",
          str(scratch.resolve()) in [str(p.resolve()) for p in found2], False)
    check("the real one under the home folder IS found",
          str((real_home2 / "JARVIS").resolve()) in [str(p.resolve()) for p in found2], True)
    check("a copy in the home folder is not temporary",
          op.is_temp(real_home2 / "JARVIS", real_home2), False)
finally:
    import shutil as _sh
    _sh.rmtree(real_home2, ignore_errors=True)
    _sh.rmtree(scratch.parent, ignore_errors=True)
many = [make_copy(home / "many" / f"copy{i}", "1.0.0") for i in range(3)]
long_text = op.report(many * 4, None, home)
check("a long list is summarised instead of printed whole",
      "showing the 8 most likely" in long_text, True)

print("\n8. no copies found is reported, not crashed")
check("find_copies on an empty home",
      op.find_copies(empty, include_self=False), [])
check("choose with nothing to choose", op.choose([], empty), None)
check("plan with nothing", op.plan([], None, empty)["park"], [])

print("\n8b. which files are the CORRECT ones — asked, not guessed")
from tools.jarvis_state import project_from_cmdline                   # noqa: E402

WIN_CMD = ('"C:\\Users\\emera\\Downloads\\JARVIS\\arcdesk-src\\.venv\\Scripts\\'
           'pythonw.exe" "C:\\Users\\emera\\Downloads\\JARVIS\\arcdesk-src\\run.py" '
           '--shadow')
check("a quoted Windows command line gives up its folder",
      project_from_cmdline(WIN_CMD).endswith("arcdesk-src"), True)
check("an unquoted one too",
      project_from_cmdline(r"C:\x\JARVIS\python.exe C:\x\JARVIS\run.py"),
      r"C:\x\JARVIS")
check("a posix one too",
      project_from_cmdline("/usr/bin/python3 /home/user/arcdesk/run.py --no-tray"),
      "/home/user/arcdesk")
check("something that is not the app gives nothing",
      project_from_cmdline("notepad.exe notes.txt"), "")

# the running copy wins over everything else, even a newer one elsewhere
live_dir = make_copy(home / "Downloads" / "JARVIS" / "arcdesk-src2", "44.0.0", venv=False)
newer = make_copy(home / "Documents" / "arcdesk-new", "99.0.0", venv=True)
copies = [live_dir, newer]
real_running = op.running_copy
op.running_copy = lambda copies: live_dir
try:
    check("the copy that is RUNNING is the one kept", op.choose(copies, home).name,
          "arcdesk-src2")
    check("…even though another copy is newer", op.choose(copies, home).resolve()
          == newer.resolve(), False)
finally:
    op.running_copy = real_running
check("with nothing running, the newest with an environment wins",
      op.choose([live_dir, newer], home).resolve(), newer.resolve())

print("\n8c. is that copy actually runnable? checked, not assumed")
check("a real copy passes the cheap checks", op.verify(live_dir)["markers"], True)
check("…and its package is seen", op.verify(live_dir)["package"], True)
check("…with no environment it says so instead of failing",
      "no environment yet" in op.verify(live_dir)["imports"], True)
half = home / "Downloads" / "half"
half.mkdir(parents=True, exist_ok=True)
(half / "run.py").write_text("", encoding="utf-8")
check("half a copy is caught", op.verify(half)["markers"], False)

print("\n8d. the keeper is copied, never moved, when it is the running copy")
src = make_copy(home / "Downloads" / "live", "44.0.0", venv=True)
(src / "__pycache__").mkdir(exist_ok=True)
dest = home / "JARVIS-COPIED"
got_copy = op.copy_project(src, dest)
check("it copies", got_copy["ok"], True)
check("…the code comes with it", (dest / "run.py").exists(), True)
check("…the environment does not (it holds absolute paths)",
      (dest / ".venv").exists(), False)
check("…nor the caches", (dest / "__pycache__").exists(), False)
check("…and the original is untouched, because moving it would be a disappearance",
      (src / "run.py").exists(), True)
check("copying onto an existing folder is refused",
      op.copy_project(src, dest)["ok"], False)

print("\n8e. the double-click route")
place = (ROOT / "ONE-PLACE.bat").read_bytes().decode("ascii", "replace")
check("there is ONE-PLACE.bat", bool(place))
check("…it scans before it changes anything",
      place.index("--report") < place.index("--apply"), True)
check("…it asks one question", "choice /C YN" in place, True)
check("…it refuses to change anything on N", ":declined" in place, True)
check("…it proves the result runs", "--verify" in place, True)
check("…and it prints the one file to click",
      "JARVIS\\JARVIS.bat" in place, True)
check("…and writes a log that outlives the window", "jarvis-one-place-log.txt" in place, True)

print("\n9. the magic screen names its strands, and explains each one")
from PySide6.QtWidgets import QApplication                              # noqa: E402
from arcdesk.theme import THEMES                                        # noqa: E402
from arcdesk.widgets.magicscreen import APPS, STRANDS, MagicScreen      # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])
check("there are six strands", len(APPS), 6)
check("every strand has a plain-English line",
      [label for label, _t in APPS if not STRANDS.get(label)], [])
check("no line is longer than 34 characters",
      [s for s in STRANDS.values() if len(s) > 34], [])
check("the two Windows ones are still honest about going outside",
      (STRANDS["BROWSER"].startswith("the web")), True)

screen = MagicScreen(THEMES["chill"])
screen.resize(1366, 768)
rects = screen._strand_rects()                                          # noqa: SLF001
check("six rectangles to click", len(rects), 6)
check("each rectangle carries label + sentence + target",
      all(rect and label and why and target for rect, label, why, target in rects))
check("they do not overlap each other",
      [(i, j) for i in range(6) for j in range(i + 1, 6)
       if rects[i][0].intersects(rects[j][0])], [])
check("none of them sits on the command box",
      [r.width() for r, *_ in rects if r.bottom() > 768 * 0.70], [])
check("the click target is the same rectangle you can see",
      rects[1][1], APPS[1][0])
hit = screen._hit(rects[1][0].center())                                 # noqa: SLF001
check("clicking it selects that strand", rects[hit][3], APPS[1][1])
check("clicking empty space selects nothing",
      screen._hit(rects[1][0].topLeft() - rects[1][0].topLeft()), -1)   # noqa: SLF001
frame = screen.grab()
check("it paints", not frame.isNull(), True)

for size in ((1024, 600), (1366, 768), (1920, 1080)):
    screen.resize(*size)
    check(f"it fits {size[0]}x{size[1]} without a strand on the command box",
          [r.width() for r, *_ in screen._strand_rects()
           if r.bottom() > size[1] * 0.72], [])

screen.close()

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
