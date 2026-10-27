"""App-side listener for the voice daemon.

Deliberately NOT QtNetwork: importing that module costs ~4-5 MB of RAM for two
sockets. A plain stdlib `socket` on a worker thread does the same job, and the
Qt signals already cross threads safely (same pattern the agent uses).

The daemon connects to us, so:
  * the daemon can crash, be reinstalled or be restarted without losing the app
  * nothing in the daemon can ever execute UI code
  * the app runs with the daemon absent and never cares

Cost when idle: one listening socket, one sleeping thread.
"""
from __future__ import annotations

import socket
import threading

from PySide6.QtCore import QObject, Signal

from . import protocol


class WakeServer(QObject):
    woke = Signal()                 # wake phrase heard
    snoozed = Signal()              # exit phrase heard ("bye jarvis")
    command = Signal(str)           # recognised speech
    status = Signal(str)            # daemon chatter
    failed = Signal(str)
    barged = Signal()               # the user talked over ARC; stop speaking
    daemon_connected = Signal(bool)

    def __init__(self, port: int = protocol.DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port = int(port)
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._clients = 0
        self._thread: threading.Thread | None = None
        self._conn: socket.socket | None = None

    # -- lifecycle -------------------------------------------------------
    def start(self) -> bool:
        if self._sock is not None:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(4)
            s.settimeout(0.5)
        except OSError as exc:
            self.failed.emit(f"wake port {self.port} unavailable: {exc}")
            return False
        self._sock = s
        self._stop.clear()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True,
                                        name="arc-wake-accept")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    @property
    def listening(self) -> bool:
        return self._sock is not None

    # -- threads ---------------------------------------------------------
    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._clients += 1
            self._safe_emit(self.daemon_connected, True)
            threading.Thread(target=self._serve, args=(conn,), daemon=True,
                             name="arc-wake-conn").start()

    def send(self, event: str, **fields) -> bool:
        """Tell the daemon something — used to close the mic while JARVIS is speaking."""
        conn = self._conn
        if conn is None:
            return False
        try:
            conn.sendall(protocol.encode(event, **fields))
            return True
        except OSError:
            return False

    def _serve(self, conn: socket.socket) -> None:
        self._conn = conn
        conn.settimeout(1.0)
        buf = b""
        try:
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = protocol.decode(line)
                    if msg:
                        self._dispatch(msg)
        finally:
            if self._conn is conn:
                self._conn = None
            try:
                conn.close()
            except OSError:
                pass
            self._clients = max(0, self._clients - 1)
            if self._clients == 0:
                self._safe_emit(self.daemon_connected, False)

    def _safe_emit(self, sig, *args) -> None:
        """During app teardown the C++ object can already be gone."""
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    # -- dispatch (runs on a worker thread; signals are queued to the GUI) --
    def _dispatch(self, msg: dict) -> None:
        ev = msg.get("event")
        if ev == "wake":
            self._safe_emit(self.woke)
        elif ev == "barge":
            self._safe_emit(self.barged)
        elif ev == "exit":
            self._safe_emit(self.snoozed)
        elif ev == "text":
            text = str(msg.get("text") or "").strip()
            if text:
                self._safe_emit(self.command, text)
        elif ev == "status":
            self._safe_emit(self.status, str(msg.get("msg") or ""))
        elif ev == "error":
            self._safe_emit(self.failed, str(msg.get("msg") or "daemon error"))
        elif ev == "hello":
            eng = msg.get("engine", "?")
            phrase = msg.get("phrase", "?")
            self._safe_emit(self.status, f'wake daemon online · {eng} · "{phrase}"')
