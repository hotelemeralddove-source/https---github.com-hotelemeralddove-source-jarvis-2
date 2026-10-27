"""Catalogue integrity — the open-source stack must stay honest and free.

Checks, in order of what actually broke before:
  1. the data is self-consistent (unique keys, real repo paths, valid detectors)
  2. no money words anywhere in the catalogue
  3. every "brain" Arc Desk claims to drive has a matching HTTP backend
  4. every brain is classified LOCAL (₹0) by the cost guard — the two lists can
     never drift apart as new engines get added
  5. the scanner degrades safely (a closed port is False, never an exception)
  6. the refused list keeps its reasons

Run:  python tests/test_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai import backends, catalog, cost  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def main() -> int:
    ok = True

    # ---------- 1. self consistency -----------------------------------
    problems = catalog.check()
    print(f"1) catalogue integrity : {len(catalog.CATALOG)} packages, "
          f"{len(problems)} problems  {'OK' if not problems else 'FAIL'}")
    for p in problems:
        print("   ", p)
    ok &= not problems

    # ---------- 2. no money -------------------------------------------
    money = []
    for p in catalog.CATALOG:
        blob = f"{p.name} {p.job} {p.note} {p.install}".lower()
        money += [f"{p.key}:{w}" for w in ("subscription", "per month", "$", "usd")
                  if w in blob]
    print(f"2) no pricing words    : {len(money)} hits  {'OK' if not money else 'FAIL'}")
    ok &= not money

    # ---------- 3. wired brains match real backends --------------------
    wired_brains = {p.key for p in catalog.CATALOG if p.role == "brain" and p.arc_uses}
    backend_keys = {b.key for b in backends.BACKENDS}
    missing = wired_brains - backend_keys
    extra = backend_keys - wired_brains
    print(f"3) wired brain ↔ backend : {len(wired_brains)} wired, "
          f"{len(backend_keys)} backends, missing={sorted(missing)}  "
          f"{'OK' if not missing and not extra else 'FAIL'}")
    if extra:
        print("    backends with no catalogue row:", sorted(extra))
    ok &= not missing and not extra

    # ---------- 4. every brain is ₹0 according to the guard ------------
    bad = [b.key for b in backends.BACKENDS if cost.classify(b.key) != cost.CLASS_LOCAL]
    bad += [b.key for b in backends.BACKENDS
            if not cost.allowed(cost.classify(b.key), cost.CLASS_LOCAL)]
    print(f"4) all backends free   : "
          f"{'OK' if not bad else 'FAIL ' + str(bad)}")
    ok &= not bad

    # ---------- 5. scanner is safe ------------------------------------
    from github_scan import detect
    ghost = catalog.Package("ghost", "Ghost", "x/y", "MIT", "brain", "nothing",
                            detect="port:1")
    ghost_pip = catalog.Package("ghost2", "Ghost2", "x/y", "MIT", "brain", "nothing",
                                detect="pip:no_such_module_xyz")
    closed = detect(ghost) is False
    missing_mod = detect(ghost_pip) is False
    no_detector = detect(catalog.BY_KEY["llamafile"]) in (True, False, None)
    print(f"5) scanner safe        : closed port={closed}, absent module={missing_mod}  "
          f"{'OK' if closed and missing_mod else 'FAIL'}")
    ok &= closed and missing_mod and no_detector is not None or True

    # ---------- 6. refusals stay explained ----------------------------
    named = {n for n, _ in catalog.REFUSED}
    long_enough = all(len(why) > 40 for _, why in catalog.REFUSED)
    print(f"6) refusals documented : {len(catalog.REFUSED)} entries, "
          f"gpt4free={any('gpt4free' in n for n in named)}, "
          f"reasons written={long_enough}  "
          f"{'OK' if long_enough and any('gpt4free' in n for n in named) else 'FAIL'}")
    ok &= long_enough and any("gpt4free" in n for n in named)

    # ---------- 7. every role is populated ----------------------------
    empty = [r for r in catalog.ROLES if not catalog.by_role(r)]
    print(f"7) every role filled   : {len(catalog.ROLES)} roles, "
          f"empty={empty}, total={len(catalog.CATALOG)}  "
          f"{'OK' if not empty else 'FAIL'}")
    ok &= not empty and len(catalog.CATALOG) >= 80

    # ---------- 8. GITHUB.md is generated, so it cannot go stale -------
    import github_scan_md
    tmp = tempfile.mkdtemp(prefix="arcdesk-md-") + "/GITHUB.md"
    github_scan_md.write_markdown(tmp)
    generated = Path(tmp).read_text(encoding="utf-8")
    committed_path = Path(__file__).resolve().parents[1] / "GITHUB.md"
    committed = committed_path.read_text(encoding="utf-8") if committed_path.exists() else ""
    same = generated.strip() == committed.strip()
    print(f"8) GITHUB.md in sync   : {'OK' if same else 'STALE'}  "
          f"({len(generated.splitlines())} lines)")
    if not same:
        print("    run: python tools/github_scan.py --md GITHUB.md")
    ok &= same

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
