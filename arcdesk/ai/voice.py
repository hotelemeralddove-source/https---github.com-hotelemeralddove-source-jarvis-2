"""Voice out — using what the OS already has, so nothing bloats the app.

    Windows : PowerShell + System.Speech (built into Windows, 0 MB of our RAM, a
              separate short-lived process we can kill)
    macOS   : `say`
    Linux   : `espeak-ng` / `spd-say`

Three things this module takes seriously, because they are what makes synthetic
speech feel bad:

1. **The text is written to be read, not to be looked at.** A reply like
   "saved to arc_elephant_1792666838.png (vector sketch engine)" is unlistenable.
   `sanitise()` turns paths, symbols, code and URLs into something a voice can say.

2. **Long replies are chunked.** Speaking one 900-character blob means the process
   is alive for 60 s and cannot be interrupted at a sensible point. Chunks of about
   220 characters let the first words start sooner and let a cancel land between
   sentences.

3. **A new sentence cancels the old one.** Every `speak()` bumps a generation
   counter; the worker checks it between chunks and dies quietly if it is stale. So
   interrupting ARC mid-sentence, or a fast second reply, never produces two voices
   talking over each other.

Costs nothing, ships nothing: the engine is the one already installed on the machine.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

from .. import quiet
import sys
import threading
import time
import textwrap
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

#: Installed voices, read once per process (a PowerShell round-trip is ~300 ms).
_VOICE_CACHE: list[str] | None = None


def _sapi_lang(lang: str) -> str:
    """`ta` -> `ta-IN`, `hi` -> `hi-IN`, `en` -> `en-IN`. SAPI wants a full tag."""
    lang = (lang or "").strip().lower()
    if not lang:
        return "en-IN"
    if "-" in lang:
        return lang
    return {"ta": "ta-IN", "hi": "hi-IN", "en": "en-IN"}.get(lang, lang)

# ---------------------------------------------------------------- neural voice
# Piper: MIT-licensed neural TTS that runs on a CPU at roughly real time. It is
# ~60-120 MB per voice, so it is optional and never bundled — but when it is
# present the difference is not subtle: SAPI sounds like a satnav, this sounds
# like a person. Voices are ranked male-first because that is the brief.
PIPER_MALE = ("ryan", "alan", "joe", "bryce", "danny", "rohan", "pratham", "arctic")
PIPER_FEMALE = ("amy", "cori", "alba", "priyamvada", "kathleen", "lessac", "jenny")


def piper_dirs() -> list:
    """Every place we look for .onnx voices, most specific first.

    A user who already runs Piper for something else should not have to copy
    their models: we look where Piper itself puts them, then where we do.
    """
    home = Path.home()
    out = []
    env = os.environ.get("ARCDESK_PIPER_DIR")
    if env:
        out.append(Path(env))
    # ARCDESK_HOME is "this copy's data folder" — a portable checkout, or a test run. It
    # was ignored here, so a test that downloaded voices wrote 236 MB into the real
    # %APPDATA%\ArcDesk folder (and that is what filled the workspace budget). It comes
    # first, and when it is set it is the ONLY app folder we use.
    sandbox_home = (os.environ.get("ARCDESK_HOME") or "").strip()
    if sandbox_home:
        out.append(Path(sandbox_home) / "ArcDesk" / "voices")
        out += [
            home / ".local" / "piper",       # voices the person already owns are still
            home / ".config" / "piper",      # found, they are read-only for us
            Path.cwd() / "voices",
        ]
        seen, unique = set(), []
        for d in out:
            key = str(d)
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return unique
    out += [
        Path(os.environ.get("APPDATA", home)) / "ArcDesk" / "voices",
        Path(os.environ.get("LOCALAPPDATA", home)) / "ArcDesk" / "voices",
        home / ".local" / "share" / "arcdesk" / "voices",
        home / ".local" / "piper",           # `piper --download-dir ~/.local/piper`
        home / ".config" / "piper",
        Path.cwd() / "voices",
    ]
    seen, unique = set(), []
    for d in out:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def piper_dir() -> Path:
    """The voice folder we will actually read: the first one that has a voice."""
    dirs = piper_dirs()
    for d in dirs:
        try:
            if d.is_dir() and any(d.glob("*.onnx")):
                return d
        except OSError:
            continue
    return dirs[0]


def _spec_exists(name: str) -> bool:
    """Is the package there? find_spec — it reads the file system and imports nothing.

    This matters: piper brings onnxruntime, and importing that inside the Qt process can
    end the process with no traceback (OMP/DLL clash). So the app never imports it to
    find out whether it exists.
    """
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:                                            # noqa: BLE001
        return False


def piper_available() -> bool:
    if not _spec_exists("piper"):
        # Not in this process. It may be in the app's engine folder (the Install button
        # writes a flag there) or in a python the person installed it into from a
        # terminal. Both are checked WITHOUT importing anything — one is a file, the other
        # is a cached answer, because this runs every time a sentence is spoken.
        try:
            from .. import engines, piper_engine
            where = engines.sidecar_ready("piper") or piper_engine.known_python()
        except Exception:                                        # noqa: BLE001
            where = False
        if not where:
            try:
                from .. import piper_engine
                piper_engine.discover_async()        # answers in the background, for later
            except Exception:                                    # noqa: BLE001
                pass
            return False
    return bool(piper_voices())


def piper_voices() -> list:
    """Installed .onnx voices. Empty when the folder or the package is missing."""
    found: list = []
    for d in piper_dirs():
        try:
            if d.is_dir():
                found += sorted(d.glob("*.onnx"))
        except OSError:
            continue
    return found


def pick_voice(lang: str = "en", manly: bool = True):
    """Best installed Piper voice for a language. Male voices first, on request."""
    wanted = {"en": ("en_US", "en_GB", "en_"), "ta": ("ta_",), "hi": ("hi_",)}.get(lang, ("en_",))
    pool = [v for v in piper_voices()
            if any(part in v.name for part in wanted)] or piper_voices()
    if not pool:
        return None

    def score(path) -> int:
        name = path.name.lower()
        s = 0
        if manly and any(m in name for m in PIPER_MALE):
            s += 10
        if not manly and any(f in name for f in PIPER_FEMALE):
            s += 10
        if "high" in name:
            s += 3
        elif "medium" in name:
            s += 2
        return s
    return max(pool, key=score)

SPEAK_LIMIT = 900          # characters actually spoken, not the whole answer
CHUNK = 170                # characters per utterance. It used to be 220, and 220 of
                           # English is a single breathless sentence-group: the words run
                           # together and the listener loses the thread. Short utterances
                           # with a small pause between them is what "porumaya pesu" means.

#: How long JARVIS waits between sentences. 0.18 s is the difference between dictation
#: and someone talking to you; below ~0.12 s it sounds like a machine reading a list.
PAUSE_MS = 180

#: SAPI's Rate is -10..10. +1 (the old default) is noticeably brisk; a slower delivery is
#: clearer and it was the user's first complaint ("speed ah pesuthu, ena solluthu nu puriyala").
DEFAULT_RATE = -2


def sapi_rate(cfg_value) -> int:
    """The Settings value (-10..10, 0 = normal) as a SAPI Rate."""
    try:
        return max(-10, min(10, int(cfg_value)))
    except (TypeError, ValueError):
        return DEFAULT_RATE


def ssml(text: str, rate: int = DEFAULT_RATE, pause_ms: int = PAUSE_MS,
         lang: str = "", voice: str = "") -> str:
    """Speakable SSML: a stated rate, a breath between sentences, escaped text.

    `SpeakSsml` is what lets System.Speech do this properly instead of being handed a raw
    string and guessing. Prosody rate is a percentage, because SAPI's integer Rate is a
    coarse step (each step is roughly 1.5x) and -2..+2 covers the useful range.
    """
    pct = int(round(rate * 12))              # -10..10 -> -120%..+120%
    body = []
    for sentence in re.split(r"(?<=[.!?…])\s+", (text or "").strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        body.append(_xml_escape(sentence))
    joined = f'<break time="{int(pause_ms)}ms"/>'.join(body) if body else ""
    voice_attr = (f'<voice name="{_xml_escape(voice)}">' if voice else "<voice>") \
        if voice else ""
    inner = f'<prosody rate="{pct:+d}%">{joined}</prosody>'
    root_attrs = f' xml:lang="{lang}"' if lang else ""
    if voice:
        return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"{root_attrs}>'
                f'<voice name="{_xml_escape(voice)}">{inner}</voice></speak>')
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"{root_attrs}>'
            f'{inner}</speak>')


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;").replace("'", "&apos;"))


#: Which installed Windows voice suits which accent. Indian English first because that is
#: where the user is: an en-IN voice reading Tamil-English is what sounds human to them,
#: while "Microsoft David" reading the same words sounds like a foreign satnav.
ACCENT_VOICES = {
    "en-IN": ("heera", "ravi", "neerja", "prabhat", "kalpana", "en-in"),
    "ta-IN": ("valluvar", "tamil", "ta-in", "heera", "ravi"),
    "hi-IN": ("hemant", "kalpana", "swara", "madhur", "hi-in"),
    "en-GB": ("george", "hazel", "susan", "en-gb"),
    "en-US": ("david", "zira", "mark", "en-us"),
}


def pick_voice(installed: list[str], accent: str = "en-IN",
               preferred: str = "") -> str:
    """Choose the most human-sounding installed voice for this accent.

    An exact name from Settings always wins. Otherwise the accent's candidates are matched
    against the installed list, case-insensitively. Empty result = let the engine decide,
    which is better than forcing the wrong one.
    """
    if preferred:
        for name in installed:
            if name.strip().lower() == preferred.strip().lower():
                return name
    want = ACCENT_VOICES.get((accent or "").strip(), ())
    lowered = [(n, n.lower()) for n in installed]
    for token in want:                       # ordered: the first match is the best match
        for name, low in lowered:
            if token in low:
                return name
    for name, low in lowered:
        if any(region in low for region in ("en-in", "ta-in", "hi-in")):
            return name
    return ""
_MAX_PROC_WAIT = 60.0

# Symbols that read as silence or nonsense if handed straight to a TTS engine.
_SYMBOLS = {
    "→": " to ", "←": " from ", "·": ", ", "—": ", ", "–": ", ", "×": " times ",
    "≥": " at least ", "≤": " at most ", "~": " about ", "&": " and ", "@": " at ",
    "₹": " rupees ", "$": " dollars ", "%": " percent ", "+": " plus ", "=": " equals ",
    "✓": " done ", "⚠": " warning ", "•": ", ", "|": ", ",
}

_HAS_TAMIL = re.compile(r"[\u0B80-\u0BFF]")
_HAS_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"(?:[A-Za-z]:\\|~?/)[^\s,;)]+")
_FILEVER = re.compile(r"\b([\w-]*?_)?v(\d+)\b")
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE0F]")


def _sayable_path(match: re.Match) -> str:
    """`C:\\Users\\me\\Pictures\\arc_elephant_17.png` → " the file arc elephant "."""
    raw = match.group(0)
    stem = raw.rstrip("/").split("/")[-1].rsplit("\\")[-1]
    stem = re.sub(r"\.[A-Za-z0-9]{1,4}$", "", stem)          # drop the extension
    stem = re.sub(r"\d{4,}", " ", stem)                      # drop timestamps
    words = [w for w in re.split(r"[_\-.]+", stem) if w and w.isalpha()]
    return f" the file {' '.join(words)} " if words else " the saved file "


def sanitise(text: str, limit: int = SPEAK_LIMIT) -> str:
    """Turn a written reply into something worth hearing."""
    out = textwrap.dedent(text or "")
    out = _EMOJI.sub(" ", out)

    # code blocks and inline code carry punctuation that reads as gibberish
    out = re.sub(r"```.*?```", " code block. ", out, flags=re.S)
    out = re.sub(r"`([^`]*)`", r"\1", out)

    # colours and hashes must go before the generic markdown strip eats the '#'
    out = _HEX.sub(" that colour ", out)

    # links and paths: name the thing, do not spell the machine path aloud
    out = _URL.sub(" a link ", out)
    out = _PATH.sub(_sayable_path, out)
    out = _FILEVER.sub(r"\1", out)          # arc_elephant_v2 -> arc_elephant

    # markdown noise
    out = re.sub(r"^\s{0,3}#{1,6}\s*", "", out, flags=re.M)
    out = re.sub(r"^\s{0,3}[-*\u2022]\s+", "", out, flags=re.M)
    out = re.sub(r"[*_#>]{1,}", " ", out)

    for bad, good in _SYMBOLS.items():
        out = out.replace(bad, good)

    out = re.sub(r"\s+([,.;:!?])", r"\1", out)   # no space before punctuation
    out = " ".join(out.split())
    if len(out) > limit:
        cut = out.rfind(". ", 0, limit)
        out = out[:cut + 1] if cut > limit * 0.4 else out[:limit].rstrip() + "…"
    return out.strip()


def chunks(text: str, size: int = CHUNK) -> list[str]:
    """Split at sentence ends where possible, never mid-word."""
    text = (text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        if not sentence:
            continue
        while len(sentence) > size:
            cut = sentence.rfind(", ", 0, size)
            if cut < size * 0.4:
                cut = sentence.rfind(" ", 0, size)
            if cut <= 0:
                cut = size
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            parts.append(sentence)
    return [p for p in parts if p]


STOP_WORDS = {
    "stop", "stop it", "stop talking", "stop speaking", "be quiet", "quiet",
    "silence", "shut up", "enough", "chup", "chup karo", "niru", "nillu",
}


def is_stop_phrase(text: str) -> bool:
    """Interrupting JARVIS should work by voice, not only by closing it."""
    return " ".join((text or "").lower().strip(" .!?").split()) in STOP_WORDS


def speech_lang(text: str) -> str:
    """Which language to ask the engine for. Empty = the engine's default."""
    if _HAS_TAMIL.search(text or ""):
        return "ta"
    if _HAS_DEVANAGARI.search(text or ""):
        return "hi"
    return ""


_PIPER_CACHE: dict = {}     # unused since fix41 (piper lives in a child process now)
_PIPER_WHY: list = []       # the last reason piper could not speak, for the log


def _note_piper(why: str) -> None:
    """Remember why the neural voice was skipped — once, quietly, for the crash log."""
    if not why:
        return
    _PIPER_WHY.append(str(why)[:200])
    del _PIPER_WHY[:-4]
    try:
        import logging
        logging.getLogger("arcdesk.piper").info("piper skipped: %s", why)
    except Exception:                                            # noqa: BLE001
        pass


#: The last few reasons a sentence did not come out of the speakers. "output audio vara
#: matiku" with nothing anywhere is the worst possible behaviour, so every skipped engine
#: writes its reason here and `Voice.explain()` reads it out.
_SAY_WHY: list[str] = []


def _note_say(why: str) -> None:
    if not why:
        return
    text = str(why)[:180]
    if text in _SAY_WHY:
        return
    _SAY_WHY.append(text)
    del _SAY_WHY[:-6]
    try:
        import logging
        logging.getLogger("arcdesk.voice").info("speech skipped: %s", text)
    except Exception:                                            # noqa: BLE001
        pass


def last_problems() -> list[str]:
    return list(_SAY_WHY)


def _temp_wav() -> str:
    import tempfile
    fd, path = tempfile.mkstemp(prefix="arc_tts_", suffix=".wav")
    os.close(fd)
    return path


class Voice:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._gen = 0
        self._worker: threading.Thread | None = None
        self._pending: list[str] = []
        self._streaming = False
        self._on_done = None

    # -- capability report ----------------------------------------------
    def tts_label(self) -> str:
        if IS_WIN:
            return "SAPI (Windows)"
        if IS_MAC:
            return "say"
        return "espeak" if (shutil.which("espeak-ng") or shutil.which("espeak")) else "none"

    def stt_label(self) -> str:
        if IS_WIN:
            return "Windows dictation"
        return "unavailable"

    @property
    def tts_available(self) -> bool:
        return self.tts_label() != "none"

    def voices(self) -> list[str]:
        """Installed system voices. Empty means the default voice only."""
        try:
            if IS_WIN:
                script = ("Add-Type -AssemblyName System.Speech;"
                          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                          "$s.GetInstalledVoices() | ForEach-Object "
                          "{ $_.VoiceInfo.Name }")
                out = quiet.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True, text=True, timeout=12, errors="replace")
                return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
            if IS_MAC:
                out = quiet.run(["say", "-v", "?"], capture_output=True,
                                     text=True, timeout=12, errors="replace")
                return [ln.split()[0] for ln in (out.stdout or "").splitlines() if ln.strip()]
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            if not exe:
                return []
            out = quiet.run([exe, "--voices"], capture_output=True,
                                 text=True, timeout=12, errors="replace")
            names = []
            for ln in (out.stdout or "").splitlines()[1:]:
                bits = ln.split()
                if len(bits) >= 2:
                    names.append(f"{bits[1]} · {bits[3] if len(bits) > 3 else ''}".strip(" ·"))
            return names
        except Exception:
            return []

    def voice_names(self) -> list[str]:
        """The SAPI voices installed on this machine (empty anywhere else)."""
        return voice_names_ensure()


    # -- speak -----------------------------------------------------------
    def speak(self, text: str, wav: str = "", on_done=None, append: bool = False) -> None:
        """Fire and forget: never blocks the UI, never raises. Cancels the previous.

        `on_done` is called when this utterance finishes or is cancelled — the window
        uses it to tell the voice daemon that the microphone can open again.

        `append=True` is streaming mode: the text joins the queue *behind* what is
        already being spoken instead of cancelling it, so ARC can start the first
        sentence while the model is still writing the third. Call `close_stream()`
        when the answer is complete, or the worker waits for more.
        """
        if wav:
            self._speak_to_file(text, wav)
            return
        ai = self.cfg.get("ai", {})
        if not ai.get("voice", True) or not (text or "").strip():
            return
        clean = sanitise(text)
        if not clean:
            return
        parts = chunks(clean)
        if append:
            with self._lock:
                if self._worker is not None and self._worker.is_alive():
                    self._pending.extend(parts)
                    return
                # nothing playing: start the stream, keep it open for more
                self._gen += 1
                gen = self._gen
                self._pending.clear()
                self._streaming = True
                self._on_done = on_done
            self._worker = threading.Thread(target=self._run, args=(parts, gen, ""),
                                            daemon=True, name="arc-tts")
            self._worker.start()
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._pending.clear()
            self._streaming = False
            self._on_done = on_done
        self._worker = threading.Thread(target=self._run, args=(parts, gen, ""),
                                        daemon=True, name="arc-tts")
        self._worker.start()

    def close_stream(self) -> None:
        """The answer is finished — let the worker exit once the queue is empty."""
        with self._lock:
            self._streaming = False

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Block until speech finishes. Used by tests and by --say, never by the UI."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)
        return not (worker is not None and worker.is_alive())

    def stop(self) -> None:
        """Silence it now — the current chunk dies, the rest never start."""
        with self._lock:
            self._gen += 1
            self._pending.clear()
            self._streaming = False
            proc = self._proc
        self._kill(proc)

    @staticmethod
    def is_stop_phrase(text: str) -> bool:
        """True for "stop", "shut up", "chup" — the user silencing JARVIS by voice."""
        return is_stop_phrase(text)

    # -- neural backend -----------------------------------------------------
    def neural_voice(self, lang: str = "en"):
        """The Piper voice that would be used, or None."""
        if not piper_available():
            return None
        return pick_voice(lang, manly=bool(self.cfg.get("ai", {}).get("voice_male", True)))

    def describe_engine(self, lang: str = "en") -> str:
        voice = self.neural_voice(lang)
        if voice is not None:
            return f"piper · {voice.stem}"
        return self.tts_label()

    def _voice_key(self, lang: str) -> str:
        """A stable name for "which engine voice is this", for the pitch cache."""
        ai = self.cfg.get("ai", {})
        return (f"{ai.get('voice_engine', 'auto')}|{ai.get('voice_name') or 'auto'}|"
                f"{lang or ai.get('voice_lang') or 'en'}")

    def _match_speak(self, text: str, lang: str) -> bool:
        """Say it in the imported clip's pitch — "my voice", without the big engine.

        Renders the sentence to a file with whichever engine can speak this language
        (piper when it has a voice for it, otherwise the Windows voice), moves it onto the
        pitch measured from the person's own clip, and plays that. No download, no GPU.
        """
        try:
            from .. import voicematch
        except Exception:                                        # noqa: BLE001
            return False
        try:
            if not voicematch.active(self.cfg):
                return False
            prof = voicematch.reference_profile()
            if not prof:
                _note_say("your clip is too short to measure a voice from (1.5 s of "
                          "speech is the minimum)")
                return False
            src = _temp_wav()
            dst = _temp_wav()
            # render to a file: wav=... means "do not play", so this cannot loop back here
            if not self._speak_blocking(text, src):
                _note_say("no engine on this PC could render that sentence")
                return False
            got = voicematch.match_file(src, dst, prof, tts_key=self._voice_key(lang))
            if not got.get("ok"):
                _note_say(f"voice match failed: {got.get('why', '')}")
                return False
            if not self._play_file(dst):
                _note_say("the matched sentence was made but the speakers did not play it")
                return False
            return True
        except Exception as exc:                                 # noqa: BLE001
            _note_say(f"voice match crashed: {type(exc).__name__}: {exc}")
            return False
        finally:
            for name in ("src", "dst"):
                path = locals().get(name, "")
                if path and not path.endswith("last_tts.wav"):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    def explain(self, text: str = "") -> str:
        """One line, for the settings window and the console: what will speak, and if
        nothing will, why not. The complaint was "output audio vara matiku" with no
        message anywhere — this is the message."""
        try:
            from .. import clone, voicematch
            lang = speech_lang(text) or str(self.cfg.get("ai", {}).get("voice_lang") or "en")
            ref = clone.reference()
            # cached_only: a full probe takes minutes on a machine that has the engine,
            # and "Hear the reply voice now" sits on this line with the button disabled
            # - the settings dialog read as hung. The arc-warm thread refreshes the
            # cache in the background; a cold cache here means "say nothing new".
            ready = [k for k, v in clone.engines(cached_only=True).items()
                     if v.get("available")]
            if ref and ready:
                return f"your clip, exact clone ({ready[0]}) — {lang}"
            if ref and voicematch.active(self.cfg):
                prof = voicematch.reference_profile()
                return (f"your clip, matched voice · {prof.get('pitch') or '?'} Hz "
                        f"{lang} — no engine needed")
            if ref:
                return ("a clip is imported but matching is off — turn on \"Speak in my "
                        "voice\" in Settings")
            if self.neural_voice(lang):
                return f"neural voice ({lang})"
            if IS_WIN:
                return f"the Windows voice ({lang})"
            return "no voice engine on this machine"
        except Exception as exc:                                 # noqa: BLE001
            return f"could not tell ({type(exc).__name__}: {exc})"

    def _clone_speak(self, text: str, lang: str, wav: str = "") -> bool:
        """Speak in the voice the person imported. False = engine not ready."""
        try:
            from .. import clone
        except Exception:
            return False
        if not clone.reference() or clone.route(lang) not in ("indicf5", "xtts"):
            return False          # nothing to clone with; the chain moves on
        return clone.speak(text, lang, wav)

    def _piper_speak(self, text: str, lang: str, wav: str = "") -> bool:
        """Synthesize with Piper in a CHILD process, then play the file.

        Not in this process, on purpose: loading onnxruntime into a running Qt app is what
        used to close the window with no message (see arcdesk/piper_engine.py). Here a
        piper problem costs one sentence — the voice chain moves on to the next engine.
        """
        voice_path = self.neural_voice(lang)
        if voice_path is None:
            return False
        try:
            from .. import piper_engine

            # a touch slower and a touch heavier: this is the "manly" dial
            depth = float(self.cfg.get("ai", {}).get("voice_depth", 1.06))
            out = wav or str(_temp_wav())
            got = piper_engine.speak(text, str(voice_path), out,
                                     length_scale=max(0.85, min(depth, 1.35)))
            if not got.get("ok"):
                _note_piper(got.get("why", ""))
                return False
            return True if wav else self._play_file(out)
        except Exception as exc:                                 # noqa: BLE001
            _note_piper(f"{type(exc).__name__}: {exc}")
            return False

    def _play_file(self, path: str) -> bool:
        try:
            if IS_WIN:
                cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle",
                       "Hidden", "-Command",
                       f"(New-Object Media.SoundPlayer '{path}').PlaySync()"]
            elif IS_MAC:
                cmd = ["afplay", path]
            else:
                player = shutil.which("aplay") or shutil.which("paplay") or shutil.which("ffplay")
                if not player:
                    return False
                cmd = [player, path] + (["-nodisp", "-autoexit", "-loglevel", "quiet"]
                                        if player.endswith("ffplay") else [])
            return self._track(cmd, path)
        except Exception:
            return False

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    # -- internals --------------------------------------------------------
    def _next_part(self, gen: int) -> str | None:
        """Next piece of the stream — waiting a little if the model is still typing."""
        with self._lock:
            if gen != self._gen:
                return None
            if self._pending:
                return self._pending.pop(0)
            if not self._streaming:
                return None
        deadline = time.time() + 5.0        # a stalled model must not hold the mic
        while time.time() < deadline:
            time.sleep(0.05)
            with self._lock:
                if gen != self._gen:
                    return None
                if self._pending:
                    return self._pending.pop(0)
                if not self._streaming:
                    return None
        return None

    def _run(self, parts: list[str], gen: int, wav: str) -> None:
        try:
            queue = list(parts)
            while queue:
                with self._lock:
                    if gen != self._gen:      # a newer sentence silenced us
                        return
                if not self._speak_blocking(queue.pop(0), wav):
                    return
            while True:
                part = self._next_part(gen)
                if part is None:
                    return
                with self._lock:
                    if gen != self._gen:
                        return
                if not self._speak_blocking(part, wav):
                    return
        finally:
            with self._lock:
                done = getattr(self, "_on_done", None)
                self._on_done = None
            if done is not None:
                try:
                    done()
                except Exception:
                    pass

    def _speak_to_file(self, text: str, wav: str) -> None:
        """Render to a file instead of the speakers — used by tools/say.py."""
        clean = sanitise(text)
        self._speak_blocking(clean, wav)

    def _speak_blocking(self, text: str, wav: str = "") -> bool:
        ai = self.cfg.get("ai", {})
        rate = sapi_rate(ai.get("voice_rate", DEFAULT_RATE))
        name = str(ai.get("voice_name") or "")
        accent = str(ai.get("voice_accent") or "en-IN")
        pause = int(ai.get("voice_pause_ms", PAUSE_MS))
        if not name:
            name = pick_voice(self.voice_names(), accent, "")
        lang = speech_lang(text) or str(ai.get("voice_lang") or "")
        try:
            # 1. the cloned voice, when an engine and a reference clip exist
            if self.cfg.get("ai", {}).get("voice_engine", "auto") in ("auto", "clone") \
                    and self.cfg.get("ai", {}).get("voice_clone", True) \
                    and self._clone_speak(text, lang or "en", wav):
                return True
            # 1b. "my voice (quick)" — the imported clip, matched onto whatever engine can
            #     speak this language. This is what makes an imported MP3 audible TODAY,
            #     without the 2 GB clone engine. Skipped for tools that ask for a file.
            if not wav and self._match_speak(text, lang or "en"):
                return True
            # 2. piper: same language, better than SAPI, still offline
            if self.cfg.get("ai", {}).get("voice_engine", "auto") in ("auto", "piper") \
                    and self._piper_speak(text, lang or "en", wav):
                return True
            if IS_WIN:
                # SSML, not a bare string: it carries the rate and the pauses between
                # sentences, which is what makes it sound like a person rather than a
                # satnav. XML escaping happens in ssml(); here we only single-quote it
                # for PowerShell's -Command.
                doc = ssml(text, rate=rate, pause_ms=pause, lang=_sapi_lang(lang),
                           voice=name)
                safe = doc.replace("'", "''")
                s = ("Add-Type -AssemblyName System.Speech;"
                     "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                     f"$s.Rate={rate};")
                if name:
                    s += f"try{{$s.SelectVoice('{name.replace(chr(39), chr(39) * 2)}')}}catch{{}};"
                if wav:
                    s += f"$s.SetOutputToWaveFile('{wav.replace(chr(39), chr(39) * 2)}');"
                # SpeakSsml THROWS when the <voice> element names a voice this PC does not
                # have (or a language it cannot read) — and the old code discarded stderr and
                # threw the failure away, so the person heard nothing at all and was told
                # nothing. Now: try SSML, then a plain Speak() with no voice element, then a
                # plain Speak() before any voice was selected. One of the three makes sound.
                plain = text.replace("'", "''")
                s += (f"try{{$s.SpeakSsml('{safe}')}}"
                      f"catch{{$s.Speak('{plain}')}};$s.Dispose()")
                got = self._track(["powershell", "-NoProfile", "-NonInteractive",
                                   "-WindowStyle", "Hidden", "-Command", s], wav,
                                  capture_errors=True)
                if got:
                    return True
                _note_say("the Windows voice could not say it (SpeakSsml and Speak both "
                          "failed — usually a voice name that no longer exists)")
                # last resort: no voice selection, no rate, no SSML. Just sound.
                bare = ("Add-Type -AssemblyName System.Speech;"
                        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;")
                if wav:
                    bare += f"$s.SetOutputToWaveFile('{wav.replace(chr(39), chr(39) * 2)}');"
                bare += f"$s.Speak('{plain}');$s.Dispose()"
                return self._track(["powershell", "-NoProfile", "-NonInteractive",
                                    "-WindowStyle", "Hidden", "-Command", bare], wav,
                                   capture_errors=True)
            if IS_MAC:
                cmd = ["say"]
                if lang:
                    cmd += ["-v", name or lang]
                elif name:
                    cmd += ["-v", name]
                if wav:
                    cmd += ["-o", wav, "--data-format=LEI16@22050"]
                return self._track(cmd + [text], wav)
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            if not exe:
                return False
            cmd = [exe, "-s", str(165 + rate * 15)]
            if lang:
                cmd += ["-v", lang]
            if wav:
                cmd += ["-w", wav]
            return self._track(cmd + [text], wav)
        except Exception:
            return False

    def _track(self, cmd: list[str], wav: str = "", capture_errors: bool = False) -> bool:
        try:
            proc = quiet.popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE if capture_errors
                                    else subprocess.DEVNULL)
        except Exception as exc:                                     # noqa: BLE001
            _note_say(f"{type(exc).__name__}: could not start {Path(cmd[0]).name}")
            return False
        with self._lock:
            self._proc = proc
        try:
            proc.wait(timeout=_MAX_PROC_WAIT)
        except Exception:
            self._kill(proc)
            return False
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        if wav:
            try:
                ok = proc.returncode == 0 and Path(wav).exists() and Path(wav).stat().st_size > 1024
            except OSError:
                ok = False
            if not ok:
                _note_say(f"{Path(cmd[0]).name} wrote no audio"
                          + (f" (exit {proc.returncode})" if proc.returncode else ""))
            return ok
        return proc.returncode == 0

    def _kill(self, proc: subprocess.Popen | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # -- listen ------------------------------------------------------------
    def listen(self, seconds: int = 6) -> str:
        """Blocking, Windows-only, last-resort STT. Call from a worker thread."""
        if not IS_WIN:
            return ""
        safe_seconds = int(seconds)
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$r=New-Object System.Speech.Recognition.SpeechRecognitionEngine;"
            "$r.SetInputToDefaultAudioDevice();"
            "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar));"
            f"$res=$r.Recognize([TimeSpan]::FromSeconds({safe_seconds}));"
            "if($res){$res.Text}"
        )
        try:
            out = quiet.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", script],
                capture_output=True, text=True, timeout=safe_seconds + 6, errors="replace")
            return (out.stdout or "").strip()
        except Exception:
            return ""


def voice_names_cached() -> list[str] | None:
    """The installed voice names, or None when not asked for yet.

    The GUI must never be the thread that pays for the first PowerShell call
    (2-12 s on a cold Windows machine), so the caller can ask "do we know yet?"
    and only wait when it already is on a worker thread.
    """
    return _VOICE_CACHE


def voice_names_ensure() -> list[str]:
    """The names, paying for the probe if it has not happened yet. Worker threads."""
    global _VOICE_CACHE
    if _VOICE_CACHE is not None:
        return _VOICE_CACHE
    names: list[str] = []
    if IS_WIN:
        try:
            out = quiet.run(["powershell", "-NoProfile", "-NonInteractive",
                             "-WindowStyle", "Hidden", "-Command",
                             "Add-Type -AssemblyName System.Speech;"
                             "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                             ".GetInstalledVoices() | ForEach-Object "
                             "{ $_.VoiceInfo.Name }"],
                            timeout=12)
            names = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        except Exception:                                   # noqa: BLE001
            names = []
    _VOICE_CACHE = names
    return names
