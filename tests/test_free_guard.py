"""Zero-cost guard: prove Arc Desk cannot spend money without a deliberate opt-in.

Three cases:
  1. local engine (Ollama on localhost) -> allowed, classified local
  2. free tier (Groq)                    -> allowed at max_class=free
  3. paid (OpenAI key in settings)       -> REFUSED before any request, agent
                                            falls back to Lite instead of failing

Run:  QT_QPA_PLATFORM=offscreen python tests/test_free_guard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk.ai import cost  # noqa: E402
from arcdesk.ai.agent import Agent  # noqa: E402
from arcdesk.ai.llm import LLMClient, LLMError  # noqa: E402


def expect_refused(name, fn):
    try:
        fn()
    except LLMError as exc:
        print(f"  {name:26s} REFUSED ✓  ({str(exc)[:52]}…)")
        return True
    except Exception as exc:
        print(f"  {name:26s} wrong error: {exc}")
        return False
    print(f"  {name:26s} NOT refused ✗")
    return False


def main() -> int:
    QApplication.instance() or QApplication(sys.argv[:1])   # Qt needs one app object
    ok = True

    print("1) classification")
    for prov, url, want in (
        ("lite", "", "local"),
        ("ollama", "http://127.0.0.1:11434/v1", "local"),
        ("custom", "http://127.0.0.1:8080/v1", "local"),
        ("groq", "https://api.groq.com/openai/v1", "free"),
        ("openai", "https://api.openai.com/v1", "paid"),
        ("custom", "https://paid-proxy.example.com/v1", "paid"),
    ):
        got = cost.classify(prov, url)
        mark = "✓" if got == want else "✗"
        if got != want:
            ok = False
        print(f"  {prov:8s} {url[:36]:38s} {got:6s} {mark}")

    print("\n2) client construction under max_class=free")
    guard = {"enabled": True, "max_class": "free"}
    ok &= expect_refused("openai key",
                         lambda: LLMClient.from_config(
                             {"provider": "openai", "api_key": "sk-test"}, guard))
    ok &= expect_refused("paid custom url",
                         lambda: LLMClient.from_config(
                             {"provider": "custom", "api_key": "x",
                              "base_url": "https://paid-proxy.example.com/v1"}, guard))

    for label, cfg in (("lite", {"provider": "lite"}),
                       ("ollama", {"provider": "ollama"}),
                       ("groq", {"provider": "groq", "api_key": "gsk_test"})):
        try:
            c = LLMClient.from_config(cfg, guard)
            print(f"  {label:26s} allowed   ✓  -> {cost.classify(c.provider, c.base_url)}")
        except LLMError as exc:
            print(f"  {label:26s} wrongly refused ✗ {exc}")
            ok = False

    print("\n3) agent falls back instead of dying")
    agent = Agent({"ai": {"enabled": True, "provider": "openai", "api_key": "sk-x",
                          "voice": False},
                   "cost": guard})
    agent.context_fn = lambda: "test"
    heard: dict[str, str] = {}
    agent.error.connect(lambda e: heard.setdefault("error", e))
    agent.reply.connect(lambda r: heard.setdefault("reply", r))
    loop = QEventLoop()
    agent.reply.connect(lambda *_: loop.quit())
    agent.error.connect(lambda *_: loop.quit())
    QTimer.singleShot(15_000, loop.quit)
    agent.ask("system report")
    loop.exec()

    fell_back = agent.brain == "lite"
    answered = bool(heard.get("reply"))
    print("  error surfaced :", (heard.get("error") or "")[:70])
    print("  brain now      :", agent.brain)
    print("  answered anyway:", answered)
    ok &= fell_back and answered

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    # The checks have all printed their verdict by the time main() returns. What happens
    # next is Qt tearing down a QApplication while the agent's worker thread is still
    # unwinding, which faults inside libQt6Core on some builds (exit code 139) *after* a
    # clean PASS — the runner then reported a green test as FAIL. Leaving the process here
    # keeps the verdict honest: the suite is not hiding a failure, it is refusing to die
    # in Qt's destructor. The app's own quit path is covered by test_app_lifecycle and
    # tools/voice_roundtrip, which run a real app and watch it close.
    _code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
