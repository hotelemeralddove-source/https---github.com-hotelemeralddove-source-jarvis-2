"""Make every window fit the screen it is shown on, and stay reachable.

The complaint that made this file exist: *"even screen ah viitu veliya poiruku app size,
so enakku minimize pana, expand pana, screen size adjust panra mathiri, scroll pani all
details ayum pakura mathiri"* — and before that, a setup card whose **submit button was
below the bottom edge of the screen**, which reads as "there is no submit button".

The rules here are the ones a window should have followed from the start:

  * a dialog never starts taller or wider than the usable screen (minus a small margin
    for the taskbar and window borders);
  * its body scrolls, so nothing can be unreachable on a small laptop;
  * the action row (Done / Start / Save) is pinned outside the scroll, so the button that
    finishes the job is *always* on screen;
  * the maximum button is offered, so "expand" is possible, and the window can also be
    dragged smaller — the minimum is a floor, not a size.

Everything is measured against `QScreen.availableGeometry()` rather than a hard-coded
number, because 1366x768 at 125% scaling is not 1366 pixels wide and a laptop with a
docked second screen is even less predictable.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QLayout, QScrollArea, QSizeGrip, QVBoxLayout, QWidget,
)

#: How much of the screen a window may use. Windows' own windows leave a similar margin.
FILL = 0.90


def available(widget: QWidget | None = None) -> QRect | None:
    """The usable area of the screen the window is (or will be) on."""
    try:
        screen = None
        if widget is not None:
            handle = widget.windowHandle()
            screen = handle.screen() if handle is not None else None
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else None
    except Exception:                                            # noqa: BLE001
        return None


def fit_dialog(dialog: QDialog, preferred: tuple[int, int] = (740, 640),
               minimum: tuple[int, int] = (420, 300), margin: int = 24) -> None:
    """Size `dialog` to the screen, then move it fully inside it.

    Called after the layout is built, so `sizeHint()` knows how tall the content really
    wants to be; `preferred` is only an upper bound.
    """
    area = available(dialog)
    if area is None:                                   # no screen (tests, offscreen)
        dialog.resize(*preferred)
        return
    max_w = max(minimum[0], int(area.width() * FILL) - margin)
    max_h = max(minimum[1], int(area.height() * FILL) - margin)
    want_w = min(preferred[0], max_w)
    want_h = min(preferred[1], max_h)
    # `sizeHint()` is what the CONTENT would like; `minimumSizeHint()` is what it truly
    # needs. Asking for the hint is what produced
    #     QWindowsWindow::setGeometry: Unable to set geometry 705x720 … Resulting 705x743
    # on a Windows screen whose work area is shorter than the dialog's wish. A dialog only
    # grows past `preferred` when the widgets genuinely cannot shrink, and never past the
    # work area — the rule for every window, on every laptop screen.
    needs = dialog.minimumSizeHint()
    want_h = min(max(want_h, min(needs.height(), max_h)), max_h)
    want_w = min(max(want_w, min(needs.width(), max_w)), max_w)
    # A minimum larger than the screen is the bug this file is about: clamp it.
    dialog.setMinimumSize(min(minimum[0], max_w), min(minimum[1], max_h))
    # The ceiling is the WORK AREA (not 90 % of it), so "expand" still fills the screen.
    dialog.setMaximumSize(area.width(), area.height())
    dialog.resize(want_w, want_h)
    x = area.x() + (area.width() - want_w) // 2
    y = area.y() + max(8, (area.height() - want_h) // 2)
    dialog.move(max(area.x(), x), max(area.y(), y))
    # "expand pana" — the maximum button, and the dialog is resizable by its edges.
    dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    dialog.setSizeGripEnabled(True)


def scroll_body(dialog: QDialog, keep_last: int = 1) -> QScrollArea | None:
    """Wrap a dialog's body in a scroll area, leaving the last `keep_last` items pinned.

    The pinned items are the action row (Done / Save / Start). Keeping them outside the
    scroll is the whole point: on a short screen the body scrolls and the button that
    finishes the job is still visible.
    """
    lay = dialog.layout()
    if lay is None:
        return None
    count = lay.count()
    movable = count - max(0, keep_last)
    if movable <= 0:
        return None

    # Without this, Qt's default SetDefaultConstraint copies the body's *minimum* height
    # back onto the dialog — the scroll area would exist and the dialog would still be
    # too tall for the screen.
    lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    inner = QWidget()
    inner.setMinimumHeight(0)
    inner_lay = QVBoxLayout(inner)
    inner_lay.setContentsMargins(0, 0, 6, 0)          # room for the scrollbar
    inner_lay.setSpacing(max(6, lay.spacing()))

    moved = []
    for _ in range(movable):
        item = lay.takeAt(0)
        if item is not None:
            moved.append(item)
    for item in moved:
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            inner_lay.addWidget(widget)
        elif child is not None:
            inner_lay.addLayout(child)
        else:
            inner_lay.addStretch(item.sizeHint().height() or 0)
    inner_lay.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(inner)
    scroll.setMinimumHeight(120)          # it may shrink; it may not disappear
    scroll.setMinimumWidth(0)
    lay.insertWidget(0, scroll, 1)
    return scroll


def make_fit(dialog: QDialog, preferred: tuple[int, int] = (740, 640),
             keep_last: int = 1, minimum: tuple[int, int] = (420, 300)) -> None:
    """One call for a dialog: scroll the body, pin the action row, fit the screen."""
    scroll_body(dialog, keep_last=keep_last)
    fit_dialog(dialog, preferred=preferred, minimum=minimum)


def add_size_grip(window: QWidget) -> QSizeGrip | None:
    """A draggable resize corner for frameless windows.

    The main window is frameless (that is the look), and a frameless window on Windows
    cannot be resized by its edges — so without this the size was whatever it started as.
    """
    lay = window.layout()
    if lay is None:
        return None
    grip = QSizeGrip(window)
    grip.setFixedSize(16, 16)
    grip.setToolTip("drag to resize")
    if isinstance(lay, QVBoxLayout):
        lay.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
    else:                                            # Qt's own layout, not ours
        grip.move(window.width() - 18, window.height() - 18)
        grip.raise_()
    return grip


def clamp_to_screen(window: QWidget) -> None:
    """After restoring a saved geometry: make sure it is still on this screen.

    A window remembered from a 27-inch monitor opens mostly off-screen on a laptop, and
    the person's only clue is "the app is not there". Same idea for a window taller than
    the screen: shrink it to fit instead of letting the bottom fall off.
    """
    area = available(window)
    if area is None:
        return
    min_w, min_h = max(360, int(area.width() * 0.45)), max(280, int(area.height() * 0.45))
    window.setMinimumSize(min(window.minimumWidth(), min_w),
                          min(window.minimumHeight(), min_h))
    w = min(window.width(), area.width())
    h = min(window.height(), area.height())
    window.resize(max(min_w, w), max(min_h, h))
    x = min(max(window.x(), area.x()), area.right() - window.width() + 1)
    y = min(max(window.y(), area.y()), area.bottom() - window.height() + 1)
    window.move(max(area.x(), x), max(area.y(), y))
