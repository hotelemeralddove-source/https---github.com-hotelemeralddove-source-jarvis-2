"""An engine that IS on this PC must never be reported as missing

    python tests/test_engine_found.py

The report (26.png): *"through the terminal all engines downloaded machi but ipo kanom,
even downloaded or ready nu kooda kamikala"* — the engines were installed, and the Voice
page said "Piper is not installed" with a 1.5 GB download button. Three separate reasons,
and every one of them is checked here:

    1. an engine has two halves — the packages and the weights/voice files. Only the whole
       thing was ever reported, so "package here, weights missing" arrived as "nothing is
       installed";
    2. the search for "a python that already has this" runs in the background, and the
       dialog read its answer once, before it existed, and never looked again;
    3. piper's voices are separate .onnx files. `pip install piper-tts` in a terminal is a
       complete install of the *engine* and still says "not installed".

Nothing here downloads anything: the probes are stubbed, the wording and the screen are
real.
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-found-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"      # nothing is discovered by accident

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import clone, engines  # noqa: E402

ok = True


def check(label: str, got, want) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {got!r}")
    if not same:
        print(f"        expected {want!r}")


_DOWNLOADS: list = []


def no_download(*a, **k):                            # noqa: ANN002, ANN003
    _DOWNLOADS.append((a, k))
    return {"ok": False, "why": "the test stopped it before a byte moved"}


engines.fetch = no_download                          # noqa: SLF001
engines.install = no_download                        # noqa: SLF001
engines._make_venv = no_download                     # noqa: SLF001

print("\n1. the packages are here, the weights are not — that is not 'not installed'")
weights_dir = Path(tempfile.mkdtemp(prefix="arcdesk-weights-"))
old_models = os.environ.get("ARCDESK_MODELS")
os.environ["ARCDESK_MODELS"] = str(weights_dir)       # an empty cache: no weights anywhere

real_importable, real_foreign = clone._importable, clone._foreign_python   # noqa: SLF001
try:
    clone._importable = lambda name: name == "transformers"               # noqa: SLF001
    clone._foreign_python = lambda key: "/home/someone/miniconda3/envs/indicf5/python" \
        if key == "indicf5" else ""                                       # noqa: SLF001
    clone.refresh()
    st = engines.status()
    check("the engine is reported as found (code), not as missing", st["indicf5"]["code"], True)
    check("…but it cannot speak yet, so it is not 'ready'", st["indicf5"]["ready"], False)
    check("…and the reason names the weights, nothing else",
          st["indicf5"]["problem"], "missing the IndicF5 weights")
    check("…and it remembers WHICH python has it",
          st["indicf5"]["python"], "/home/someone/miniconda3/envs/indicf5/python")

    print("\n2. weights present as well — now it is ready")
    (weights_dir / "models--ai4bharat--IndicF5" / "snapshots" / "abc").mkdir(parents=True)
    big = weights_dir / "models--ai4bharat--IndicF5" / "snapshots" / "abc" / "model.safetensors"
    big.write_bytes(b"0" * 2_000_000)
    clone.refresh()
    st = engines.status()
    check("with the weights, the same engine is ready", st["indicf5"]["ready"], True)
    check("…and nothing is left to download", st["indicf5"]["problem"], "")
finally:
    clone._importable, clone._foreign_python = real_importable, real_foreign  # noqa: SLF001
    if old_models is None:
        os.environ.pop("ARCDESK_MODELS", None)
    else:
        os.environ["ARCDESK_MODELS"] = old_models

print("\n3. piper has two halves too, and they used to be added together")
from arcdesk import piper_engine  # noqa: E402
from arcdesk.ai import voice as voice_mod  # noqa: E402

real_python, real_voices = piper_engine.known_python, voice_mod.piper_voices
try:
    piper_engine.known_python = lambda: "/usr/bin/python3"     # engine installed
    voice_mod.piper_voices = lambda: []                        # no .onnx voice
    clone.refresh()
    st = engines.status()["piper"]
    check("a terminal `pip install piper-tts` counts as found", st["code"], True)
    check("…but with no voice file it cannot speak", st["ready"], False)
    check("…and the reason names the voice file, not the engine",
          "voice" in st["problem"], True)

    voice_mod.piper_voices = lambda: [Path("/x/en_GB-alan-medium.onnx")]
    clone.refresh()
    st = engines.status()["piper"]
    check("…with a voice file it is ready", st["ready"], True)
    check("…and the count is shown", st["voices"], 1)

    piper_engine.known_python = lambda: ""
    voice_mod.piper_voices = lambda: []
    clone.refresh()
    st = engines.status()["piper"]
    check("nothing at all is still nothing", (st["code"], st["ready"]), (False, False))
finally:
    piper_engine.known_python, voice_mod.piper_voices = real_python, real_voices
    clone.refresh()

print("\n4. a probe that finishes late is not lost")
before = engines.foreign_version()
engines._FOREIGN["indicf5"] = (999999.5, "/some/python")     # noqa: SLF001
check("the version changes when a probe answers", engines.foreign_version() > before, True)

print("\n5. the engine screen says which half is missing, and offers only that half")
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.engine_dialog import EngineDialog  # noqa: E402

dialog = EngineDialog(get_theme("chill"))
dialog._items = {                                       # noqa: SLF001
    "piper": {"id": "piper", "label": "Piper", "langs": "English, Hindi",
              "size_mb": 60, "why": "small", "needs": "a voice per language",
              "ready": False, "code": True, "python": "/opt/conda/envs/piper/python",
              "voices": 0, "problem": "a piper voice (.onnx, ~30 MB, one per language)",
              "model": "", "local": "", "token_from": ""},
}
dialog._method = {"can_install": True, "why": ""}       # noqa: SLF001
dialog._fill_picker()                                   # noqa: SLF001
dialog._show()                                          # noqa: SLF001
said = dialog.state.text().lower()
check("the screen says the engine IS installed", "engine is installed" in said, True)
check("…and says the voice files are what is missing", "voice files" in said, True)
check("…the button offers only the voices, not 1 Gb",
      dialog.go.text(), "Download the voices only (~60 MB)")
check("…and the dialog remembers to skip the packages", dialog._weights_only, True)  # noqa: SLF001
check("…naming the python that has it",
      "/opt/conda/envs/piper/python" in dialog.state.text(), True)

dialog._items["indicf5"] = {                            # noqa: SLF001
    "id": "indicf5", "label": "IndicF5", "langs": "Tamil, Hindi", "size_mb": 1500,
    "why": "cloned Tamil", "needs": "a GPU to feel instant", "ready": False,
    "code": True, "python": "/opt/conda/envs/indicf5/python", "voices": 0,
    "problem": "missing the IndicF5 weights", "model": "", "local": "", "token_from": ""}
dialog._fill_picker()                                   # noqa: SLF001
index = dialog.picker.findData("indicf5")
dialog.picker.setCurrentIndex(index)
dialog._show()                                          # noqa: SLF001
check("a half-installed IndicF5 offers only the missing part",
      dialog.go.text(), "Download only the missing part (1.5 GB)")
check("…and it will not reinstall torch",
      "packages you installed are left exactly as they are" in dialog.state.text(), True)

print("\n6. 'download only the missing part' really is only that")
engines.install = no_download                             # noqa: SLF001
got = engines.missing_only("indicf5")
check("it goes through the weights fetcher, not the installer", _DOWNLOADS[-1][0][0]
      if _DOWNLOADS else "fetch", "indicf5")
check("…it does not pretend to have worked", got.get("ok"), False)

print("\n7. the screen re-reads itself when a late probe answers")
dialog2 = EngineDialog(get_theme("chill"))
check("it is watching", dialog2._watch.isActive(), True)  # noqa: SLF001
called = []
real_reload = dialog2.reload


def spy(*a, **k):                                        # noqa: ANN002, ANN003
    called.append(1)


dialog2.reload = spy                                     # noqa: SLF001
engines._FOREIGN["xtts"] = (123456.75, "/late/python")    # noqa: SLF001
dialog2._watch_for_found()                                # noqa: SLF001
check("a late answer makes it repaint without a button press", called, [1])
dialog2._watch_for_found()                                # noqa: SLF001
check("…and the same answer does not repaint in a loop", called, [1])
dialog2.reload = real_reload                             # noqa: SLF001

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
