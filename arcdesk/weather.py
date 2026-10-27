"""Optional weather via Open-Meteo (no API key, no account).

Design rules for the "must stay offline-safe" requirement:
  * Disabled by default -> the app never opens a socket.
  * When enabled: single background thread, 6 s timeout, hard try/except.
  * Result cached to disk; on network failure the HUD keeps the last known
    reading instead of breaking the UI.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import config

WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers",
    81: "Showers", 82: "Violent showers", 95: "Thunderstorm",
    96: "Thunder + hail", 99: "Thunder + hail",
}


class WeatherService(QObject):
    updated = Signal(str, bool)  # text, ok

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._last_fetch = 0.0

    def refresh(self, lat: float, lon: float, city: str, refresh_min: int = 20) -> None:
        if self._busy:
            return
        if time.time() - self._last_fetch < refresh_min * 60:
            return
        self._busy = True
        threading.Thread(target=self._work, args=(lat, lon, city),
                         daemon=True, name="arc-weather").start()

    # runs on a worker thread; Qt queues the signal back to the UI thread
    def _work(self, lat: float, lon: float, city: str) -> None:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat:.4f}&longitude={lon:.4f}"
               "&current=temperature_2m,weather_code&timezone=auto")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ArcDesk/0.1"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cur = data.get("current") or {}
            temp = float(cur.get("temperature_2m"))
            label = WMO.get(int(cur.get("weather_code", -1)), "Weather")
            text = f"{city} · {temp:.0f}°C · {label}"
            self._last_fetch = time.time()
            try:
                config.weather_cache_path().write_text(
                    json.dumps({"text": text, "ts": self._last_fetch}), "utf-8")
            except Exception:
                pass
            self.updated.emit(text, True)
        except Exception as exc:  # offline, DNS blocked, timeout, bad JSON...
            cached = self._cached()
            if cached:
                self.updated.emit(cached + " · CACHED", False)
            else:
                self.updated.emit(f"WEATHER UNAVAILABLE ({type(exc).__name__})", False)
        finally:
            self._busy = False

    @staticmethod
    def _cached() -> str | None:
        try:
            data = json.loads(config.weather_cache_path().read_text("utf-8"))
            if time.time() - float(data.get("ts", 0)) < 6 * 3600:
                return str(data.get("text") or "") or None
        except Exception:
            return None
        return None
