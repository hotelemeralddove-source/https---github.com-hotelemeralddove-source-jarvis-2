"""Themes = power modes.

Each mode carries its own palette, animation budget and frame cap.
That is how "Gaming Mode pauses heavy effects" actually works: it drops
the frame rate to 10 fps and the effect scale to 0.15, so the desktop
effects stop competing with your game for the GPU.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    hint: str
    bg: str          # window base
    panel: str       # card fill
    accent: str      # primary neon
    accent2: str     # secondary neon
    text: str        # primary text
    dim: str         # secondary text / borders
    effects: float   # 0.0 - 1.0 glow + animation intensity
    fps: int         # animation frame cap

    def q(self, attr: str, alpha: int | None = None) -> QColor:
        c = QColor(getattr(self, attr))
        if alpha is not None:
            c.setAlpha(max(0, min(255, int(alpha))))
        return c


THEMES: dict[str, Theme] = {
    "focus": Theme(
        key="focus", label="Focus",
        hint="distractions off",
        bg="#04080f", panel="#0a1420",
        accent="#38bdf8", accent2="#60a5fa",
        text="#e2f2ff", dim="#31526e",
        effects=0.35, fps=20,
    ),
    "chill": Theme(
        key="chill", label="Chill",
        hint="ambience on",
        bg="#050b12", panel="#0b1622",
        accent="#22d3ee", accent2="#a78bfa",
        text="#e6fbff", dim="#33566b",
        effects=1.0, fps=30,
    ),
    "gaming": Theme(
        key="gaming", label="Gaming",
        hint="effects paused",
        bg="#0d0703", panel="#1a0f06",
        accent="#f97316", accent2="#ef4444",
        text="#fff1e2", dim="#6b4426",
        effects=0.15, fps=10,
    ),
    "night": Theme(
        key="night", label="Night",
        hint="dimmed low light",
        bg="#08060a", panel="#120e18",
        accent="#f59e0b", accent2="#fb7185",
        text="#ffe9c9", dim="#5c4527",
        effects=0.3, fps=12,
    ),
}

MODE_ORDER = ("focus", "chill", "gaming", "night")


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["chill"])


def tuned(key: str, effects: float | None = None) -> Theme:
    """The mode's theme, with the user's own effects intensity laid over it.

    `config["effects"]` used to be written and never read — a setting you could change
    with nothing happening. It now means one thing: how much glow the world draws.
    None keeps the mode's own value (the default), 0.0 turns the glow off for a weak
    GPU or a laptop on battery, 1.0 is everything.
    """
    th = get_theme(key)
    if effects is None:
        return th
    try:
        value = max(0.0, min(1.0, float(effects)))
    except (TypeError, ValueError):
        return th
    from dataclasses import replace
    return replace(th, effects=value)


def next_mode(key: str) -> str:
    try:
        i = MODE_ORDER.index(key)
    except ValueError:
        return MODE_ORDER[1]
    return MODE_ORDER[(i + 1) % len(MODE_ORDER)]
