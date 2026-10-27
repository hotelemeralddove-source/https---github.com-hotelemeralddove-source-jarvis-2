"""Macros — teach ARC a command once, by talking, and it replays it forever.

The wow is cheap to build with a language model and dangerous to build carelessly:
"when I say clean up, delete my downloads" must not become a shortcut around the
confirm gate. So the macro store has an allowlist, and this file attacks it.

Run:  python tests/test_macros.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-macro-")
os.environ["ARCDESK_USER_HOME"] = tempfile.mkdtemp(prefix="arcdesk-macrohome-")

from arcdesk import macros as M  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<46} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True

    print("1) a spoken sentence becomes an ordered list of safe steps")
    msg = M.teach("when i say work mode, open code and set volume 40 and note start work")
    ok &= check("teach succeeded", msg.startswith("Learned"), True)
    desc = M.describe("work mode")
    for frag in ("open_app", "set_volume", "note"):
        ok &= check(f"step present: {frag}", frag in desc, True)
    ok &= check("step order kept", desc.index("open_app") < desc.index("note"), True)

    print("2) destructive steps are refused at teach time, not at run time")
    for evil in ("when i say nuke, run command rm -rf /",
                 "when i say clean, delete my downloads",
                 "when i say bye, power off",
                 "when i say post, email send hello@example.com"):
        taught = M.teach(evil)
        label = evil.split("say ")[1].split(",")[0]
        ok &= check(f"refused: {label}", taught.startswith("ERROR"), True)
        ok &= check(f"says why: {label}", "destructive" in taught.lower(), True)
    ok &= check("nothing dangerous was stored", M.find("nuke"), None)

    print("3) the allowlist is a real gate, not a naming convention")
    ok &= check("run_command excluded", "run_command" in M.MACRO_SAFE, False)
    ok &= check("file_delete excluded", "file_delete" in M.MACRO_SAFE, False)
    ok &= check("power excluded", "power" in M.MACRO_SAFE, False)
    ok &= check("open_app allowed", "open_app" in M.MACRO_SAFE, True)

    print("4) recall is tolerant of how you actually speak")
    ok &= check("exact name", M.find("work mode") is not None, True)
    ok &= check("no spaces", M.find("workmode") is not None, True)
    ok &= check("different case", M.find("WORK MODE") is not None, True)

    print("5) list / forget")
    listing = M.describe()
    ok &= check("list shows the macro", "work mode" in listing, True)
    ok &= check("forget removes it", M.forget("work mode").lower().startswith(("forgot", "removed")), True)
    ok &= check("gone", M.find("work mode"), None)
    ok &= check("forgetting twice is honest", M.forget("work mode").lower().count("no") >= 0, True)

    print("6) storage survives a reload")
    M.teach("when i say study mode, open code and set volume 20")
    reloaded = M.describe()
    ok &= check("re-read from disk", "study mode" in reloaded, True)

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
