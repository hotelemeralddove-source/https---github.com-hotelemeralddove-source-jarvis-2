"""Is my setup really free? Answer in one command.

    python tools/free_ai_check.py

Checks, in order:
  1. which local engines are running (they cost nothing)
  2. whether any configured brain would cost money (and whether the guard blocks it)
  3. what the current cost limit is
  4. a plain table of what is free forever vs optional

Exit code 0 = you cannot be charged by this configuration.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import config  # noqa: E402
from arcdesk.ai import backends, cost  # noqa: E402

OK = "  [ok]"
WARN = "  [!] "


def main() -> int:
    cfg = config.load()
    ai = cfg.get("ai", {})
    cost_cfg = cfg.get("cost", {})
    max_class = str(cost_cfg.get("max_class") or "free")

    print("Arc Desk · zero-cost check")
    print("=" * 58)

    # 1 -- local engines
    print("\nlocal engines (free forever, no account):")
    found = backends.probe()
    if found:
        for d in found:
            model = d.models[0] if d.models else "(no model loaded)"
            print(f"{OK} {d.backend.label:20s} {d.base_url:32s} {model}")
    else:
        print("  none running right now.")
        print("  free options:  ollama pull llama3.2:3b   (see setup_free_ai.bat)")
        print("  or use ARC Lite with nothing installed at all.")

    # 2 -- configured brain
    provider = str(ai.get("provider") or "auto")
    base = str(ai.get("base_url") or "")
    print("\nconfigured brain:")
    if provider == "auto":
        local = backends.best_local()
        if local:
            cls_ = cost.CLASS_LOCAL
            print(f"{OK} auto -> {local.describe()}  ({cost.LABELS[cls_]})")
        else:
            cls_ = cost.CLASS_LOCAL
            print(f"{OK} auto -> ARC Lite (FREE · LOCAL)")
    else:
        cls_ = cost.classify(provider, base)
        label = cost.LABELS[cls_]
        allowed = cost.allowed(cls_, max_class)
        if cls_ == cost.CLASS_PAID and not allowed:
            print(f"{WARN}{provider} is PAID — blocked by the guard, requests refused")
        elif cls_ == cost.CLASS_PAID:
            print(f"{WARN}{provider} is PAID and allowed — this CAN charge you")
        else:
            print(f"{OK} {provider}  ({label})")

    # 3 -- the limit
    print(f"\ncost limit: max_class = '{max_class}'  "
          f"(local = offline only, free = free tiers ok, paid = may charge)")
    if max_class == cost.CLASS_PAID:
        print(f"{WARN}paid providers are permitted by this setting")

    # 4 -- the table
    print("\nwhat costs what:")
    for what, price, note in cost.free_summary():
        print(f"  {what:28s} {price:22s} {note}")

    charged = (cls_ == cost.CLASS_PAID and max_class == cost.CLASS_PAID)
    print("\nRESULT:", "You CANNOT be charged by this configuration."
          if not charged else "Paid providers are ENABLED — you can be charged.")
    return 0 if not charged else 1


if __name__ == "__main__":
    raise SystemExit(main())
