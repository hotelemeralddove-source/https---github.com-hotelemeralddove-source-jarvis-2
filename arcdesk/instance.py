"""One Arc Desk at a time.

The launcher makes double-starts likely: the wake daemon starts the app, and the
user may also double-click the shortcut a second later. Two reactors, two mic
listeners and two magic screens fighting over one wallpaper is exactly the kind
of bug that looks like a crash.

How it works, with no extra dependency:

  * the first instance binds ``127.0.0.1:<wake_port + 1>`` and keeps it open
  * a later instance cannot bind it, so it sends ``{"event": "wake"}`` to the
    owner and exits quietly
  * the owner turns that into the normal fullscreen "HEY JARVIS" arrival

That means saying "Hey Jarvis" while the app is already running no longer risks
a second copy — it just comes to the front.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
from typing import Callable

LIVE = threading.Event()

# Windows-only, and absent from `socket` on other platforms.
_EXCLUSIVE = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)


def lock_socket_options(sock, platform: str | None = None) -> list[str]:
    """Make `bind()` refuse a second copy — and mean it on Windows.

    SO_REUSEADDR is what every tutorial sets, and on Windows it does the *opposite* of
    what it does on Linux: Windows lets a second socket bind an address that is already
    in use, so both processes believe they are the only one. Measured on the user's
    laptop (ArcDeskDiag.txt, section 6): **two** ArcDesk.exe processes, ~100 MB each.
    Two windows, two tray icons, two microphone listeners, and whichever one is in front
    is a coin toss.

    SO_EXCLUSIVEADDRUSE exists on Windows for exactly this, and must be set before bind.
    Returns the option names applied, so a test can assert the branch without Windows.
    """
    platform = platform or sys.platform
    applied = []
    if platform == "win32":
        if _EXCLUSIVE is not None:
            sock.setsockopt(socket.SOL_SOCKET, _EXCLUSIVE, 1)
            applied.append("SO_EXCLUSIVEADDRUSE")
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        applied.append("SO_REUSEADDR")
    return applied


def port_file():
    """Where the running copy writes the port it really took.

    Why a file: the launcher has to find a *working* app, and guessing from settings is
    fragile (different ARCDESK_HOME, an edited settings file, a second profile). The app
    writes its actual port here when it takes the lock and removes the file on the way
    out, so "is it up, and where?" has one honest answer.
    """
    try:
        from .config import data_dir
        return data_dir() / "lockport.txt"
    except Exception:                                            # noqa: BLE001
        return None


def recorded_port() -> int:
    """The port the last running copy left behind (0 if there is nothing recorded)."""
    path = port_file()
    try:
        if path is not None and path.exists():
            return int((path.read_text(encoding="utf-8") or "0").strip() or 0)
    except Exception:                                            # noqa: BLE001
        pass
    return 0


def lock_port(cfg: dict) -> int:
    inst = cfg.get("instance", {}) or {}
    explicit = int(inst.get("port", 0) or 0)
    if explicit:
        return explicit
    wake = int((cfg.get("wake", {}) or {}).get("port", 8765) or 8765)
    return min(wake + 1, 65534)


def ask(port: int, event: str = "wake", connect: float = 1.2,
        wait: float = 2.5) -> dict:
    """Send one event to the running copy and wait for its answer.

    Why an answer and not just a write: the socket used to accept the wake and the
    launcher called that success. If the app was alive but did not act on it — the real
    case, because the message arrived before the window existed, or the wake went down
    the "show the cinematic" path and drew nothing — the launcher printed
    *"JARVIS was already running - brought it to the front"* with no window on screen.
    That is the report: **"jarvis.bat double click pana terminal open aaguthu, jarvis run
    aaga matiku"**.

    Returns ``{"sent", "ack", "handled", "reply", "port", "error"}``:
      * ``sent``    — a connection was made and the message left
      * ``ack``     — the app answered for itself (proof it is not a hung socket)
      * ``handled`` — it says it acted on it (it does not claim a window is visible;
                      the launcher checks the log for that separately)
    """
    result = {"sent": False, "ack": False, "handled": False, "reply": None,
              "port": port, "error": ""}
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=connect) as sock:
            sock.sendall(json.dumps({"event": event, "from": "second-instance"}
                                    ).encode("utf-8") + b"\n")
            result["sent"] = True
            sock.settimeout(wait)
            data = b""
            while b"\n" not in data and len(data) < 4096:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                data += chunk
    except OSError as exc:
        result["error"] = type(exc).__name__
        return result

    try:
        reply = json.loads((data or b"{}").decode("utf-8", "replace") or "{}")
    except ValueError:
        reply = {}
    if isinstance(reply, dict) and reply.get("event"):
        result["reply"] = reply
        result["ack"] = True
        result["handled"] = bool(reply.get("handled"))
    return result


def _send_wake(port: int, timeout: float = 0.6) -> bool:
    """True only when the running app answered the wake (not merely accepted bytes)."""
    return bool(ask(port, connect=timeout).get("ack"))


class Instance:
    """Holds the listening socket for the lifetime of the process."""

    def __init__(self, cfg: dict, on_summon: Callable[[], None] | None = None):
        self.port = lock_port(cfg)
        self.on_summon = on_summon
        self.on_quit: Callable[[], None] | None = None
        self.sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------- lifecycle
    def acquire(self) -> bool:
        """True if we are the first instance, False if one already exists."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            lock_socket_options(s)
            s.bind(("127.0.0.1", self.port))
            s.listen(2)
        except OSError:
            s.close()
            return False
        self.sock = s
        LIVE.set()
        try:
            path = port_file()
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(self.port), encoding="utf-8")
        except Exception:                                        # noqa: BLE001
            pass
        self._thread = threading.Thread(target=self._serve, name="instance",
                                        daemon=True)
        self._thread.start()
        return True

    def _serve(self) -> None:
        assert self.sock is not None
        self.sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.settimeout(0.5)
                data = b""
                while b"\n" not in data and len(data) < 4096:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                event = json.loads(data.decode("utf-8", "replace") or "{}").get("event")
                if event:
                    try:
                        import logging
                        logging.getLogger("arcdesk.instance").info("lock event: %s -> %s",
                                                                   event,
                                                                   "handled"
                                                                   if (event in ("wake", "show")
                                                                       and self.on_summon)
                                                                   or (event == "quit"
                                                                       and self.on_quit)
                                                                   else "IGNORED")
                    except Exception:                            # noqa: BLE001
                        pass
                handled = False
                if event in ("wake", "show") and self.on_summon:
                    self.on_summon()
                    handled = True
                elif event == "quit" and self.on_quit:
                    # a launcher or an updater asking the app to step aside. Doing it
                    # this way means nothing has to be killed: no lost settings, no
                    # half-written file, and no other python program on the PC is
                    # touched (which is what "taskkill /IM pythonw.exe" used to do).
                    self.on_quit()
                    handled = True
                # Answer, always. A launcher that cannot tell "handled" from "ignored"
                # has to guess, and guessing wrong is what a silent failure is made of.
                try:
                    # The name must describe what happened, not what was asked: an
                    # unhandled event that answers "bye" is a lie the launcher would
                    # believe.
                    name = ("ignored" if not handled
                            else ("bye" if event == "quit" else "awake"))
                    reply = {"event": name, "handled": handled}
                    conn.sendall(json.dumps(reply).encode("utf-8") + b"\n")
                except OSError:
                    pass
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def release(self) -> None:
        self._stop.set()
        try:
            path = port_file()
            if path is not None and path.exists():
                path.unlink()
        except Exception:                                        # noqa: BLE001
            pass
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        LIVE.clear()


def another_instance_running(cfg: dict) -> bool:
    """True when a second copy exists *and* has been told to wake up."""
    return _send_wake(lock_port(cfg))


def is_live() -> bool:
    return LIVE.is_set()


def wake_now(cfg: dict, tries: int = 3, gap: float = 0.5) -> dict:
    """Ask any running copy to show itself, retrying briefly.

    The retries are not superstition: a wake that lands while the first copy is still
    building its window (about a second after login, when autostart and a double-click
    can collide) is dropped, because there is nothing to connect the signal to yet.
    Three tries over ~1.5 s covers that window.
    """
    port = recorded_port() or lock_port(cfg)
    last = {"sent": False, "ack": False, "handled": False, "reply": None,
            "port": port, "error": "never tried"}
    for attempt in range(max(1, tries)):
        last = ask(port)
        if last.get("ack"):
            return last
        if attempt + 1 < tries:
            threading.Event().wait(gap)
    return last
