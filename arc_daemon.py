"""Arc Desk voice daemon — the ears, in their own process.

WHY A SEPARATE PROCESS
  Continuous microphone monitoring keeps an audio buffer, a recogniser and a
  model resident. Putting that inside Arc Desk would blow the RAM budget we
  promised to protect. So it lives here: you can watch it in Task Manager, kill
  it, or simply not run it. The main app is unaffected either way.

WHAT IS OURS AND WHAT IS BORROWED
  Ours     : the daemon, the wake/command state machine, the protocol, the
             phrase handling, the app integration, the UI.
  Borrowed : the speech engine (Vosk — Apache-2.0) and optionally the wake-word
             engine (openWakeWord — Apache-2.0). They are libraries used in the
             backend, exactly like using a JSON parser. No third-party app, UI
             or layout is copied, and none of their code is shipped as ours.
  See CREDITS.md.

RUN
  python arc_daemon.py                       # needs Arc Desk running first
  python arc_daemon.py --phrase "hey jarvis"
  python arc_daemon.py --download-model      # fetch the 40 MB Vosk model
  python arc_daemon.py --simulate "open notepad"   # no mic needed, for testing
  python arc_daemon.py --level               # show mic level, for troubleshooting
"""
from __future__ import annotations

import argparse
import json
import queue
import socket
import signal
import sys
import threading
import time
import urllib.request
from pathlib import Path

from arcdesk import config
from arcdesk.wake import protocol

SAMPLE_RATE = 16000
BLOCK = 4000            # 250 ms of audio per read
SILENCE_RMS = 380       # int16 energy below this counts as silence
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def log(msg: str) -> None:
    print(f"[arc-voice] {msg}", flush=True)


# --------------------------------------------------------------- transport
class Link:
    """Client connection back to the Arc Desk window, with reconnect."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.sock: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self, timeout: float = 3.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=1.5)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock = s
                return True
            except OSError:
                time.sleep(0.4)
        return False

    def read_loop(self, on_message) -> None:
        """Control messages from the app (currently: mute the mic while it speaks)."""
        while self.sock is not None:
            try:
                data = self.sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            for line in data.split(b"\n"):
                if not line.strip():
                    continue
                msg = protocol.decode(line)
                if msg:
                    on_message(msg)

    def send(self, event: str, **fields) -> bool:
        with self._lock:
            if self.sock is None:
                return False
            try:
                self.sock.sendall(protocol.encode(event, **fields))
                return True
            except OSError:
                self.sock = None
                return False

    def close(self) -> None:
        with self._lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None


# -------------------------------------------------------------------- audio
class Mic:
    """16 kHz mono int16 capture. sounddevice first, pyaudio as fallback."""

    def __init__(self) -> None:
        self.backend = ""
        self.q: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._stream = None
        self._pa = None

    def open(self) -> bool:
        try:
            import sounddevice as sd  # type: ignore
            def cb(indata, frames, t, status):  # noqa: ANN001
                try:
                    self.q.put_nowait(bytes(indata))
                except queue.Full:
                    pass
            self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK,
                                             dtype="int16", channels=1, callback=cb)
            self._stream.start()
            self.backend = "sounddevice"
            return True
        except Exception as exc:
            log(f"sounddevice unavailable ({type(exc).__name__})")
        try:
            import pyaudio  # type: ignore
            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(format=pyaudio.paInt16, channels=1,
                                         rate=SAMPLE_RATE, input=True,
                                         frames_per_buffer=BLOCK)
            self.backend = "pyaudio"
            return True
        except Exception as exc:
            log(f"pyaudio unavailable ({type(exc).__name__})")
        return False

    def read(self) -> bytes:
        try:
            return self.q.get(timeout=2.0)
        except queue.Empty:
            return b""

    def close(self) -> None:
        try:
            if getattr(self._stream, "stop", None):
                self._stream.stop()
            if getattr(self._stream, "close", None):
                self._stream.close()
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass


def rms(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    try:
        import audioop
        return audioop.rms(chunk, 2)
    except Exception:
        total = 0
        n = len(chunk) // 2
        if not n:
            return 0.0
        for i in range(0, len(chunk) - 1, 2):
            v = int.from_bytes(chunk[i:i + 2], "little", signed=True)
            total += v * v
        return (total / n) ** 0.5


# ------------------------------------------------------------------ engines
class VoskEngine:
    """Grammar-limited recognition: the phrase is a whitelist, not a trained model.

    This is the trick that makes a CUSTOM wake word free: change the phrase in
    settings and it works, no training, no data, no cloud.
    """

    name = "vosk"

    def __init__(self, model_dir: Path, phrase: str, exit_phrase: str = "") -> None:
        self.model_dir = model_dir
        self.phrase = phrase.strip().lower()
        self.exit_phrase = (exit_phrase or "").strip().lower()
        self._model = None

    def load(self) -> bool:
        if not self.model_dir.exists():
            log(f"model missing: {self.model_dir}")
            log("run:  python arc_daemon.py --download-model")
            return False
        try:
            import vosk  # type: ignore
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(str(self.model_dir))
            self._vosk = vosk
            return True
        except Exception as exc:
            log(f"vosk failed to load: {type(exc).__name__}: {exc}")
            return False

    def wake_recognizer(self):
        words = [self.phrase]
        if self.exit_phrase:
            words.append(self.exit_phrase)
        grammar = json.dumps(words + ["[unk]"])
        return self._vosk.KaldiRecognizer(self._model, SAMPLE_RATE, grammar)

    def command_recognizer(self):
        return self._vosk.KaldiRecognizer(self._model, SAMPLE_RATE)


class OpenWakeWordEngine:
    """Optional. Uses the openWakeWord pretrained 'hey_jarvis' model."""

    name = "openwakeword"

    def __init__(self, phrase: str) -> None:
        self.phrase = phrase.strip().lower()
        self._model = None

    def load(self) -> bool:
        try:
            from openwakeword.model import Model  # type: ignore
            key = self.phrase.replace(" ", "_")
            try:
                self._model = Model(wakeword_models=[key], inference_framework="onnx")
            except Exception:
                self._model = Model()
            self._key = key
            return True
        except Exception as exc:
            log(f"openWakeWord unavailable ({type(exc).__name__}). "
                "pip install openwakeword onnxruntime")
            return False

    def detect(self, chunk: bytes) -> str | None:
        import numpy as np  # type: ignore
        audio = np.frombuffer(chunk, dtype=np.int16)
        scores = self._model.predict(audio)
        for key, score in (scores or {}).items():
            if score >= 0.5 and "jarvis" in key.lower():
                return key
        return None


# -------------------------------------------------------------- daemon loop
class VoiceDaemon:
    def __init__(self, args) -> None:
        self.args = args
        self.phrase = (args.phrase or "hey jarvis").strip().lower()
        self.exit_phrase = (getattr(args, "exit_phrase", "") or "bye jarvis").strip().lower()
        self.link = Link(args.port)
        self.mic = Mic()
        self.engine_name = ""
        self.engine = None
        self._stop = threading.Event()
        self._mic_muted = False       # set by the app while it speaks
        self._last_spoken = ""        # the last thing JARVIS said (echo guard)
        self._last_heard_text = ""    # the last command (repeat guard)
        self._last_heard_at = 0.0
        self._noise_floor = 60        # learned from the room in the first second

    # -- setup ----------------------------------------------------------
    def _pick_engine(self) -> bool:
        want = self.args.engine
        model_dir = Path(self.args.model_dir) if self.args.model_dir else \
            config.data_dir() / MODEL_NAME

        if want in ("auto", "openwakeword"):
            ow = OpenWakeWordEngine(self.phrase)
            if ow.load() and "jarvis" in self.phrase:
                self.engine = ow
                self.engine_name = "openwakeword"
                log("wake engine: openWakeWord (pretrained hey_jarvis)")
                self._stt = VoskEngine(model_dir, self.phrase, self.exit_phrase)
                if not self._stt.load():
                    self._stt = None
                    log("no Vosk model: wake works, spoken commands will not")
                return True

        vk = VoskEngine(model_dir, self.phrase, self.exit_phrase)
        if vk.load():
            self.engine = vk
            self.engine_name = "vosk"
            self._stt = vk
            log(f"wake engine: Vosk grammar · wake = \"{self.phrase}\" · "
                f"exit = \"{self.exit_phrase}\"")
            return True
        return False

    # -- main -----------------------------------------------------------
    def run(self) -> int:
        if self.args.download_model:
            return self.download_model()

        if self.args.launcher_app:
            return self.run_launcher()

        if self.args.simulate_exit:
            return self.simulate_exit()
        if self.args.simulate:
            return self.simulate(self.args.simulate)

        log(f"connecting to Arc Desk on 127.0.0.1:{self.args.port} …")
        if not self.link.connect(timeout=25):
            log("Arc Desk is not listening. Start the app first "
                "(the daemon needs it as the receiver).")
            return 3

        if not self._pick_engine():
            self.link.send("error", msg="no speech engine available")
            return 4

        if self.args.level:
            return self.level_meter()

        if not self.mic.open():
            self.link.send("error",
                           msg="no microphone access (pip install sounddevice)")
            log("no microphone. Install with: pip install sounddevice")
            return 5

        signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        try:
            signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        except Exception:
            pass

        self.link.send("hello", engine=self.engine_name, phrase=self.phrase,
                       backend=self.mic.backend)
        log(f"listening for \"{self.phrase}\" via {self.mic.backend} · "
            f"command window {self.args.command_seconds}s · Ctrl+C to stop")
        self.link.send("status", msg=f"listening for \"{self.phrase}\"")

        try:
            self._loop()
        finally:
            self.mic.close()
            self.link.close()
        return 0

    def _loop(self) -> None:
        if self.engine_name == "openwakeword":
            self._loop_oww()
        else:
            self._loop_vosk()

    # -- vosk: detect and transcribe with the same cheap engine ----------
    def _loop_vosk(self) -> None:
        wake_rec = self.engine.wake_recognizer()
        while not self._stop.is_set():
            chunk = self.mic.read()
            if not chunk:
                continue
            if wake_rec.AcceptWaveform(chunk):
                text = json.loads(wake_rec.Result() or "{}").get("text", "")
                kind = self._which(text)
                if kind == "exit":
                    self._handle_exit()
                    wake_rec = self.engine.wake_recognizer()
                elif kind == "wake":
                    self._handle_wake()
                    wake_rec = self.engine.wake_recognizer()
            else:
                partial = json.loads(wake_rec.PartialResult() or "{}").get("partial", "")
                kind = self._which(partial)
                if kind == "exit":
                    self._handle_exit()
                    wake_rec = self.engine.wake_recognizer()
                elif kind == "wake":
                    self._handle_wake()
                    wake_rec = self.engine.wake_recognizer()

    # -- oww: cheap detector, then vosk for the command ------------------
    def _loop_oww(self) -> None:
        while not self._stop.is_set():
            chunk = self.mic.read()
            if chunk and self.engine.detect(chunk):
                self._handle_wake()

    def _phrase_in(self, text: str, target: str) -> bool:
        # exact -> token-wise -> fuzzy ("jervis", "jarvas", "a jarvis")
        from arcdesk.wake import phrases
        return phrases.contains_phrase(text, target, fuzzy=not self.args.no_fuzzy)

    def _which(self, text: str) -> str:
        """"wake", "exit" or "" — exit is checked first so "bye jarvis" never
        gets mistaken for a wake word."""
        from arcdesk.wake import phrases
        return phrases.which(text, self.phrase, self.exit_phrase,
                             fuzzy=not self.args.no_fuzzy)

    def _matches(self, text: str) -> bool:
        return self._which(text) == "wake"

    def _handle_exit(self) -> None:
        log("exit phrase detected")
        self.link.send("exit")
        self.link.send("status", msg="returning to normal")

    def _on_control(self, msg: dict) -> None:
        if msg.get("event") == "said":
            # the app tells us what it is about to say, so a speaker tail picked up after
            # the mute lifts can be recognised as ours instead of becoming a new question
            self._last_spoken = str(msg.get("text") or "")[-400:]
            return
        if msg.get("event") == "mic":
            self._mic_muted = str(msg.get("state", "on")) == "off"
            log("mic muted (JARVIS is speaking)" if self._mic_muted else "mic open")

    def _listen_for_barge(self) -> bool:
        """While JARVIS is speaking, is the user talking over it?

        Runs only while the app says the mic is "muted" for speech output — which
        really means "discard what you hear", not "stop reading the device", so the
        audio is still there to measure.
        """
        try:
            from arcdesk.wake import talk
        except Exception:
            return False
        levels: list[int] = []
        floor = getattr(self, "_noise_floor", 60)
        for _ in range(12):                     # ~1.2 s of frames
            if not self._mic_muted or self._stop.is_set():
                break
            chunk = self.mic.read()
            if not chunk:
                continue
            level = rms(chunk)
            levels.append(level)
            if talk.is_barge(levels, threshold=talk.barge_threshold(floor)):
                log("barge-in detected — the user is talking over me")
                self.link.send("barge")
                return True
        return False

    def converse(self) -> None:
        """Stay in the conversation: after an answer, listen again without a wake word.

        This is what makes it a conversation instead of a command line. The window
        mutes the microphone while it speaks, so ARC never transcribes itself; when
        the reply ends the mic opens again and the user can just keep talking.
        """
        turns = int(getattr(self.args, "converse_turns", 6) or 6)
        for _ in range(max(0, turns - 1)):
            if self._stop.is_set():
                return
            time.sleep(float(getattr(self.args, "reply_wait", 1.6) or 1.6))
            # wait for the app to finish speaking — unless the user cuts in
            waited = 0.0
            barged = False
            while self._mic_muted and waited < 30.0 and not self._stop.is_set():
                if getattr(self.args, "barge_in", True) and self._listen_for_barge():
                    barged = True
                    break
                time.sleep(0.1)
                waited += 0.1
            if barged:
                self._mic_muted = False      # the app already stopped talking
            text, audio = self.capture_command(
                seconds=min(6.0, float(self.args.command_seconds)), keep_audio=True)
            if text and not self._speaker_ok(audio):
                return
            if text:
                ok, why = self._worth_acting_on(text)
                if not ok:
                    self.link.send("status", msg=why)
                    return
            if not text:
                log("conversation ended (silence)")
                self.link.send("status", msg="conversation ended")
                return
            try:
                from arcdesk.wake import talk
                if talk.ends_conversation(text):
                    log(f"conversation closed by the user: {text}")
                    self.link.send("status", msg="chat closed")
                    self.link.send("snooze")
                    return
            except Exception:
                pass
            kind = self._which(text)
            if kind == "exit":
                log(f"exit phrase: {text}")
                self.link.send("exit")
                return
            log(f"heard (follow-up): {text}")
            self.link.send("text", text=text)

    def _handle_wake(self) -> None:
        try:
            from arcdesk.wake import phrases
            log(f'wake word detected (match {phrases.confidence(getattr(self, "_last_heard", ""), self.phrase):.2f})')
        except Exception:
            log("wake word detected")
        self.link.send("wake")
        self.link.send("status", msg="listening for your command")
        time.sleep(0.25)          # let the tail of the wake word drain
        text, audio = self.capture_command(keep_audio=True)
        if text and not self._speaker_ok(audio):
            return
        if text:
            ok, why = self._worth_acting_on(text)
            if not ok:
                self.link.send("status", msg=why)
                return
            log(f"heard: {text}")
            self.link.send("text", text=text)
            if getattr(self.args, "converse", False):
                self.converse()
        else:
            log("no command recognised")
            self.link.send("status", msg="nothing heard")

    def _worth_acting_on(self, text: str) -> tuple[bool, str]:
        """Should this sentence be acted on? (echo of our own voice / same sentence twice).

        Both failure modes were heard as "it repeats itself and gets confused": the ears
        catching the tail of JARVIS's own answer, and the recogniser handing the same
        sentence over twice for one question.
        """
        from arcdesk.wake import talk
        said = (text or "").strip()
        if not said:
            return False, "nothing heard"
        last_spoken = getattr(self, "_last_spoken", "")
        if talk.said_myself(said, last_spoken):
            log(f"ignored: that was my own voice ({said[:40]})")
            return False, "that was my own voice"
        previous = getattr(self, "_last_heard_text", "")
        when = getattr(self, "_last_heard_at", 0.0)
        if talk.is_repeat(said, previous, time.time() - when):
            log(f"ignored: same sentence twice ({said[:40]})")
            return False, "you already said that"
        self._last_heard_text = said
        self._last_heard_at = time.time()
        return True, ""

    def _speaker_ok(self, wav: str) -> bool:
        """Is the person who just spoke the one enrolled on THIS machine?

        Off unless `--voice-lock` was passed. A convenience filter, not a security
        control: it keeps your family and the television out, not a recording of you.
        """
        if not getattr(self.args, "voice_lock", False):
            return True
        try:
            from arcdesk import voiceid
        except Exception as exc:                                # noqa: BLE001
            log(f"voice lock: {exc}")
            return True
        if not voiceid.profiles():
            return True                       # nothing enrolled — do not lock anyone out
        verdict = voiceid.verify(wav)
        if verdict["allowed"]:
            log(f"voice lock: {verdict['who']} ({verdict['score']:.2f})")
            return True
        log(f"voice lock: rejected ({verdict.get('why', '')}) — not acting on it")
        self.link.send("status", msg="not your voice — ignored")
        return False

    def capture_command(self, seconds: float | None = None,
                        keep_audio: bool = False):
        """Transcribe the command. With keep_audio, also return a 16 kHz WAV path."""
        if not getattr(self, "_stt", None):
            return ("", "") if keep_audio else ""
        from arcdesk.wake import talk
        rec = self._stt.command_recognizer()
        chunks: list[bytes] = []
        # Patience. This used to be one flat deadline (7 s) with a hard 1.1 s tail, which
        # cut people off in the middle of a thought — "porumaya kekanum". Now:
        #   * up to `command_seconds` for speech to START (a person thinks after "hey jarvis")
        #   * then only stop after `silence_seconds` of quiet (a breath does not end a turn)
        #   * never stop mid-sentence: keep going while the voice keeps going, to max_seconds
        wait_for_speech = float(seconds or self.args.command_seconds)
        silence_seconds = float(getattr(self.args, "silence_seconds", 1.8) or 1.8)
        max_seconds = max(wait_for_speech, float(getattr(self.args, "max_command_seconds",
                                                       30.0) or 30.0))
        started = time.time()
        quiet_since: float | None = None
        spoken = False
        while not self._stop.is_set():
            chunk = self.mic.read()
            if not chunk:
                continue
            if getattr(self, "_mic_muted", False):
                quiet_since = None
                started = time.time()      # we were not listening: the clock starts now
                continue            # JARVIS is speaking — do not transcribe our own voice
            loud = rms(chunk) > SILENCE_RMS
            now = time.time()
            if loud:
                spoken = True
                quiet_since = None
            elif spoken and quiet_since is None:
                quiet_since = now
            quiet_for = (now - quiet_since) if quiet_since else 0.0
            # the decision is a pure function, so tests/test_talk.py can hammer it
            if talk.listen_state(spoken=spoken, quiet_for=quiet_for,
                                 elapsed=now - started,
                                 wait_for_speech=wait_for_speech,
                                 silence_seconds=silence_seconds,
                                 max_seconds=max_seconds) == "stop":
                break
            rec.AcceptWaveform(chunk)
            if keep_audio:
                chunks.append(chunk)
            # be respectful of the budget while listening
            time.sleep(0.005)
        final = json.loads(rec.FinalResult() or "{}").get("text", "").strip()
        if not keep_audio:
            return final
        return final, self._write_audio(chunks)

    def _write_audio(self, chunks: list[bytes]) -> str:
        """The command audio as a 16 kHz mono WAV, for the speaker check."""
        if not chunks:
            return ""
        try:
            import tempfile
            import wave as _wave
            path = Path(tempfile.gettempdir()) / "arcdesk-voice-lock.wav"
            with _wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"".join(chunks))
            return str(path)
        except Exception:
            return ""

    # -- helpers --------------------------------------------------------
    def level_meter(self) -> int:
        if not self.mic.open():
            self.link.send("error", msg="no microphone for level test")
            return 5
        log("speak normally — Ctrl+C to stop")
        peak = 0.0
        while not self._stop.is_set():
            chunk = self.mic.read()
            if chunk:
                lvl = rms(chunk)
                peak = max(peak, lvl)
                bars = int(min(40, lvl / 300))
                sys.stdout.write("\r" + "█" * bars + " " * (40 - bars) +
                                 f"  rms={lvl:6.0f}  peak={peak:6.0f}")
                sys.stdout.flush()
        self.mic.close()
        return 0

    # ---------------------------------------------------------------- launcher
    def run_launcher(self) -> int:
        """Standalone ear: no app running yet, so wait for the wake word and
        launch the app. This is what makes "BYE JARVIS closes the app" possible:
        the app can truly exit, and something still listens for you."""
        if not self._pick_engine():
            log("no speech engine — cannot run as a background launcher")
            return 4
        if not self.mic.open():
            log("no microphone (pip install sounddevice)")
            return 5
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        try:
            signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        except Exception:
            pass
        log(f"launcher armed · waiting for \"{self.phrase}\"")
        import subprocess as _sp
        from arcdesk.paths import app_command
        while not self._stop.is_set():
            chunk = self.mic.read()
            if not chunk:
                continue
            rec = self.engine.wake_recognizer()
            if rec.AcceptWaveform(chunk):
                text = json.loads(rec.Result() or "{}").get("text", "")
            else:
                text = json.loads(rec.PartialResult() or "{}").get("partial", "")
            if not self._which(text):
                continue
            log("wake word detected — starting Arc Desk")
            try:
                _sp.Popen(app_command(show=True), close_fds=True)
            except Exception as exc:
                log(f"could not start the app: {type(exc).__name__}: {exc}")
                continue
            # the app takes over listening; hand off and exit so we do not hold
            # the microphone twice
            time.sleep(1.0)
            self.mic.close()
            return 0
        self.mic.close()
        return 0

    def simulate(self, text: str) -> int:
        """No microphone, no model: prove the app <-> daemon path works."""
        if not self.link.connect(timeout=15):
            log(f"nothing listening on {self.args.port}")
            return 3
        self.link.send("hello", engine="simulate", phrase=self.phrase)
        self.link.send("status", msg="simulated wake")
        self.link.send("wake")
        time.sleep(0.4)
        self.link.send("text", text=text)
        time.sleep(0.6)
        self.link.close()
        log(f"simulated wake + command: {text}")
        return 0

    def simulate_exit(self) -> int:
        if not self.link.connect(timeout=15):
            log(f"nothing listening on {self.args.port}")
            return 3
        self.link.send("hello", engine="simulate", phrase=self.phrase)
        self.link.send("status", msg="simulated exit phrase")
        self.link.send("exit")
        time.sleep(0.5)
        self.link.close()
        log(f"simulated exit phrase: {self.exit_phrase}")
        return 0

    def download_model(self) -> int:
        target = config.data_dir() / MODEL_NAME
        if target.exists():
            log(f"already present: {target}")
            return 0
        url = MODEL_URL
        log(f"downloading {MODEL_NAME} (~40 MB) …")
        tmp = config.data_dir() / "model.zip"
        try:
            with urllib.request.urlopen(url, timeout=60) as r, tmp.open("wb") as fh:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    block = r.read(1 << 16)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if total:
                        sys.stdout.write(f"\r  {done / 1e6:.1f} / {total / 1e6:.1f} MB")
                        sys.stdout.flush()
            import zipfile
            with zipfile.ZipFile(tmp) as z:
                z.extractall(config.data_dir())
            tmp.unlink(missing_ok=True)
            log(f"\ndone: {target}")
            return 0
        except Exception as exc:
            log(f"download failed: {type(exc).__name__}: {exc}")
            log(f"manual option: download {url} and unzip into {config.data_dir()}")
            return 6


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arc_daemon", description="Arc Desk voice daemon")
    ap.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    ap.add_argument("--phrase", default="hey jarvis", help="wake phrase (any words)")
    ap.add_argument("--exit-phrase", default="bye jarvis", help="phrase that returns to normal")
    ap.add_argument("--engine", default="auto", choices=["auto", "vosk", "openwakeword"])
    ap.add_argument("--model-dir", default="")
    ap.add_argument("--voice-lock", action="store_true",
                    help="only act on commands spoken by the person enrolled on this "
                         "machine (see tools/voice_setup.py)")
    ap.add_argument("--command-seconds", type=float, default=12.0,
                    help="how long to wait for you to START talking (default 12 s)")
    ap.add_argument("--silence-seconds", type=float, default=1.8,
                    help="silence that ends your turn once you have started (default 1.8 s; "
                         "a breath in the middle of a Tamil sentence is not the end)")
    ap.add_argument("--max-command-seconds", type=float, default=30.0,
                    help="never cut you off mid-sentence before this (default 30 s)")
    ap.add_argument("--simulate", metavar="TEXT", help="inject wake + text, no mic needed")
    ap.add_argument("--converse", action="store_true",
                    help="keep listening after each answer (hands-free conversation)")
    ap.add_argument("--no-barge-in", action="store_true",
                    help="do not listen for interruptions while speaking")
    ap.add_argument("--converse-turns", type=int, default=6,
                    help="how many back-and-forth turns before returning to wake-word only")
    ap.add_argument("--reply-wait", type=float, default=1.6,
                    help="seconds to wait for the app to start speaking before listening")
    ap.add_argument("--no-fuzzy", action="store_true",
                    help="exact phrase matching only (fewer false wakes, more misses)")
    ap.add_argument("--launcher-app", default="",
                    help="when set, the daemon waits for the wake word and starts "
                         "this app instead of talking to a running one")
    ap.add_argument("--simulate-exit", action="store_true",
                    help="inject the exit phrase instead of a command")
    ap.add_argument("--download-model", action="store_true")
    ap.add_argument("--level", action="store_true", help="microphone level meter")
    args = ap.parse_args(argv)
    return VoiceDaemon(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
