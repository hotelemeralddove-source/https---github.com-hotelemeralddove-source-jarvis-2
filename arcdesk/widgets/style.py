"""One stylesheet for the small dialogs, so they look like the app instead of a form.

The bug this fixes was visible in one screenshot: the *engine* and *ears* dialogs were
built with Qt's default theme — **white background, black text, with the white "selection"
drawn as a highlighter behind every line of the log**, because a `QPlainTextEdit` was
appended to while it had focus. Two separate faults, and both are fixed here:

* a dialog that is handed the arc theme is now actually styled with it (labels, buttons,
  the log, the combo boxes, the progress bar — one place, not five);
* a read-only log is not a document anyone selects text in, so it cannot paint itself
  white: focus stays on the button that was pressed, and selection is off.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPlainTextEdit


def _light(th, attr: str, amount: int = 150) -> str:
    return QColor(getattr(th, attr)).lighter(amount).name()


def dialog_style(th) -> str:
    """The whole look of a small dialog, from the theme it was given."""
    accent = getattr(th, "accent", "#7fe3f0")
    bg = getattr(th, "bg", "#0a1116")
    panel = getattr(th, "panel", "#101a20")
    text = getattr(th, "text", "#dbe7ec")
    dim = getattr(th, "dim", "#8fa3ad")
    dim_l = _light(th, "dim", 150)
    acc_q = QColor(accent)
    soft = f"rgba({acc_q.red()},{acc_q.green()},{acc_q.blue()},0.16)"
    return f"""
        QDialog, QWidget#dlgRoot {{ background: {bg}; }}
        QLabel {{ color: {text}; font-family: Segoe UI, Noto Sans, sans-serif;
                  background: transparent; }}
        QLabel#h1 {{ font-size: 15pt; font-weight: 600; }}
        QLabel#dim {{ color: {dim_l}; font-size: 12px; }}
        QLabel#verdict {{ color: {text}; font-size: 12px; }}
        QLabel#verdict[ok="false"] {{ color: #ef9a9a; }}
        QLabel#verdict[ok="true"] {{ color: #8ee6a4; }}
        QPlainTextEdit, QTextEdit {{
            background: {panel}; color: {dim_l};
            border: 1px solid {dim}; border-radius: 8px; padding: 6px;
            font-family: Consolas, "Cascadia Mono", monospace; font-size: 11px;
            selection-background-color: {soft}; selection-color: {text};
        }}
        QComboBox, QLineEdit {{
            background: {panel}; color: {text}; border: 1px solid {dim};
            border-radius: 8px; padding: 5px 8px;
        }}
        QComboBox:focus, QLineEdit:focus {{ border-color: {accent}; }}
        QComboBox QAbstractItemView {{ background: {panel}; color: {text};
            selection-background-color: {accent}; selection-color: #04090f; }}
        QListWidget {{
            background: {panel}; color: {text}; border: 1px solid {dim};
            border-radius: 8px; padding: 4px;
        }}
        QListWidget::item:selected {{ background: {accent}; color: #04090f; }}
        QPushButton {{
            background: {panel}; color: {text}; border: 1px solid {dim};
            border-radius: 8px; padding: 7px 14px;
        }}
        QPushButton:hover {{ border-color: {accent}; color: {accent}; }}
        QPushButton:disabled {{ color: {dim}; border-color: {panel}; }}
        QProgressBar {{
            background: {panel}; border: 1px solid {dim}; border-radius: 6px;
            height: 10px; text-align: center; color: {text};
        }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
    """


def read_only_log(widget: QPlainTextEdit) -> QPlainTextEdit:
    """A log you read, not a document you edit or select.

    `setFocusPolicy(NoFocus)` and `NoTextInteraction` are the point: the widget still
    scrolls, but it never takes the keyboard, so it cannot paint a selection highlight
    over its own text (which is exactly what the user saw) and it cannot steal focus from
    the button that started the download.
    """
    widget.setReadOnly(True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    widget.setMaximumBlockCount(4000)
    return widget
