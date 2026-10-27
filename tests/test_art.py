"""ARC Sketch — "draw an elephant" must actually produce an elephant.

Two things are tested, and the second one is why this file exists:

  1. every subject renders to a real image, and saving never overwrites
  2. editing by sentence mutates the *document*, and the article bug does not
     come back — "draw an elephant" used to parse as article="an", subject="",
     and silently drew the default instead of what was asked for

Run:  QT_QPA_PLATFORM=offscreen python tests/test_art.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import art  # noqa: E402


def main() -> int:
    ok = True

    # ---------- 1. every subject paints something ---------------------
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([sys.argv[0]])
    bad = []
    for subj in art.SUBJECTS:
        img = art.Sketch(subj).render(360, 260)
        if img.isNull() or img.width() != 360:
            bad.append(subj)
    print(f"1) {len(art.SUBJECTS)} subjects render : {len(bad)} broken  "
          f"{'OK' if not bad else 'FAIL ' + str(bad)}")
    ok &= not bad

    # ---------- 2. saving is additive --------------------------------
    tmp = tempfile.mkdtemp(prefix="arcart-")
    a = art.save_sketch(art.Sketch("elephant"), os.path.join(tmp, "same.png"))
    b = art.save_sketch(art.Sketch("elephant"), os.path.join(tmp, "same.png"))
    distinct = a != b and os.path.exists(a) and os.path.exists(b)
    print(f"2) save never overwrites  : {distinct}  {'OK' if distinct else 'FAIL'}")
    ok &= distinct

    # ---------- 3. editing by sentence -------------------------------
    sk = art.Sketch("elephant")
    cases = [
        ("make it purple", lambda s: s.accent == art.PALETTE["purple"]),
        ("make it bigger", lambda s: s.scale > 1.0),
        ("add a sun", lambda s: "sun" in s.extras),
        ("move it left", lambda s: s.dx < 0),
        ("rotate it", lambda s: s.rotate != 0),
        ("remove the sun", lambda s: "sun" not in s.extras),
    ]
    for text, check in cases:
        sk.apply(text)
        if not check(sk):
            bad.append(text)
    print(f"3) sentence edits         : {len(cases) - len(bad)}/{len(cases)} applied  "
          f"{'OK' if not bad else 'FAIL ' + str(bad)}")
    ok &= not bad

    # ---------- 4. undo ----------------------------------------------
    before = sk.scale
    sk.apply("bigger")
    grew = sk.scale > before
    undone = sk.undo() and abs(sk.scale - before) < 1e-9
    print(f"4) undo                   : grew={grew}, reverted={undone}  "
          f"{'OK' if grew and undone else 'FAIL'}")
    ok &= grew and undone

    # ---------- 5. regression: "add a sun" must not replace the elephant
    sk2 = art.Sketch("elephant")
    sk2.apply("make it purple and bigger, add a sun")
    kept = sk2.subject == "elephant" and "sun" in sk2.extras
    print(f"5) subject not hijacked   : subject={sk2.subject}, extras={sk2.extras}  "
          f"{'OK' if kept else 'FAIL'}")
    ok &= kept

    # ---------- 6. regression: the article is parsed, not swallowed ---
    parsed = []
    for phrase, want in [("draw an elephant", "elephant"), ("draw a cat", "cat"),
                         ("sketch a house", "house"), ("paint me a tree", "tree"),
                         ("turn it into a robot", "robot")]:
        s3 = art.Sketch("fish")
        s3.apply(phrase)
        if s3.subject != want:
            parsed.append(f"{phrase!r} → {s3.subject}")
    print(f"6) articles parsed        : {5 - len(parsed)}/5  "
          f"{'OK' if not parsed else 'FAIL ' + str(parsed)}")
    ok &= not parsed

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
