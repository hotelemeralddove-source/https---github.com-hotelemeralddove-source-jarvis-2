"""Inside an app — the accessibility tree, and the fall back to pixels.

The rule being tested: `ui_act` must try the fast, exact route (accessibility) and
then the universal route (read the screen and click the words), and when neither is
possible it must say which one was missing. It must never quietly do nothing.

Run:  python tests/test_uia.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("ARCDESK_USER_HOME", tempfile.mkdtemp(prefix="arcdesk-user-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import uia, vision  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def check_true(label: str, got) -> bool:
    return check(label, bool(got), True)


def main() -> int:
    ok = True

    print("1) bad requests are refused with a reason")
    ok &= check_true("no name", uia.act("").startswith("ERROR"))
    ok &= check_true("unknown action", uia.act("Send", "explode").startswith("ERROR"))
    ok &= check_true("set without a value", uia.act("Search", "set").startswith("ERROR"))

    print("2) the accessibility tree is asked first")
    real_act = getattr(uia, "_win_find_action", None)
    if sys.platform != "win32":
        # on this platform the tree is either absent or AT-SPI; both are honest
        out = uia.controls(10)
        ok &= check_true("controls() answers or explains",
                         "NO_TREE" not in out and len(out) > 0)
        ok &= check_true("the answer mentions what is missing or lists controls",
                         "accessibility tree" in out or "\t" in out or "pyatspi" in out)

    print("3) when there is no tree, it reads the screen instead")
    real_click = vision.click_text
    seen: dict = {}

    def fake_click(text, button="left", double=False, lang=""):
        seen["text"] = text
        return "found 'Send' at (10, 20) and clicked"

    vision.click_text = fake_click
    try:
        out = uia.act("Send", "click")
        if sys.platform != "win32":
            ok &= check_true("fell back to the screen", seen.get("text") == "Send")
            ok &= check_true("and said so", "reading the screen" in out)
        else:
            print("   --   Windows: the PowerShell path is primary here")
    finally:
        vision.click_text = real_click

    print("4) a miss is reported, not swallowed")
    def missing(text, button="left", double=False, lang=""):
        return "ERROR: could not find 'Nope' on screen. Visible text: hello world"

    vision.click_text = missing
    try:
        out = uia.act("Nope", "click")
        ok &= check_true("error is passed through", out.startswith("ERROR"))
        ok &= check_true("the screen text is included for the model to read",
                         "hello world" in out)
    finally:
        vision.click_text = real_click

    print("5) 'set' never falls back to clicking")
    if sys.platform != "win32":
        out = uia.act("Search", "set", "hello")
        ok &= check_true("explains the need for a tree",
                         "accessibility tree" in out or out.startswith("ERROR"))

    if real_act is None:
        pass
    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
