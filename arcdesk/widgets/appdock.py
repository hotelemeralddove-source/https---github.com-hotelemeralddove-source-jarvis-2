"""Apps that open INSIDE JARVIS, not somewhere behind it.

The report, from the magic screen: *"athula irukura notepad, calculator lan click pana athu
background la windows la than open aaguthu, enakku jarvis layae open aaganum"* — and it was
literally true: every tile called `open_app`, which starts `notepad.exe` as a separate
process. In fullscreen magic mode that process lands *under* the magic screen, so the click
looked like it did nothing.

Windows cannot be talked into embedding an arbitrary modern app (a UWP calculator has no
window handle to hand over), so the honest fix is to own the small apps outright. These
four are the ones people actually click:

    notepad     a real text pad, with open/save, inside the deck
    calc        a working calculator (keyboard included), inside the deck
    files       a folder browser that opens files with their default app
    processes   what is using the machine right now — the "why is it slow" answer

Anything else still launches as a Windows program, but it is brought to the FRONT
afterwards, so a click never ends with "nothing happened".
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog, QFileSystemModel, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QStackedWidget, QTreeView, QVBoxLayout, QWidget,
)

from .. import quiet
from ..theme import Theme


def _qss(theme: Theme) -> str:
    return f"""
    QWidget#dock {{ background: {theme.panel}; border: 1px solid {theme.accent}44;
                    border-radius: 10px; }}
    QLabel#dockTitle {{ color: {theme.accent}; font-weight: 700; letter-spacing: 2px; }}
    QLabel {{ color: {theme.text}; }}
    QPlainTextEdit, QLineEdit, QTreeView {{
        background: #061219; color: {theme.text}; border: 1px solid #1d3a46;
        selection-background-color: {theme.accent}55; }}
    QPushButton {{ background: #0d222c; color: {theme.text};
                   border: 1px solid #20404b; border-radius: 6px; padding: 5px 10px; }}
    QPushButton:hover {{ border-color: {theme.accent}; }}
    QPushButton#op {{ background: {theme.accent}; color: #05141a; font-weight: 700; }}
    """


class _Notepad(QWidget):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Write here. Ctrl+S saves, inside JARVIS.")
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.where = QLabel("unsaved")
        self.where.setObjectName("dim")
        row.addWidget(self.where, 1)
        open_btn = QPushButton("Open…")
        open_btn.clicked.connect(self._open)
        row.addWidget(open_btn)
        save = QPushButton("Save…")
        save.setObjectName("op")
        save.clicked.connect(self._save)
        row.addWidget(save)
        lay.addLayout(row)
        self._path = ""

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open a text file", "",
                                              "Text (*.txt *.md *.csv *.log *.json);;All (*)")
        if not path:
            return
        try:
            self.text.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))
            self._path = path
            self.where.setText(path)
        except OSError as exc:
            self.where.setText(f"could not read it: {exc}")

    def _save(self) -> None:
        default = self._path or str(Path.home() / "Desktop" / "jarvis-note.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save this note", default, "Text (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
            self._path = path
            self.where.setText(f"saved: {path}")
        except OSError as exc:
            self.where.setText(f"could not save: {exc}")

    def keyPressEvent(self, event) -> None:                     # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier \
                and event.key() == Qt.Key.Key_S:
            self._save()
            return
        super().keyPressEvent(event)


class _Calc(QWidget):
    """A calculator that works with the mouse and the keyboard."""

    KEYS = [["C", "(", ")", "/"],
            ["7", "8", "9", "*"],
            ["4", "5", "6", "-"],
            ["1", "2", "3", "+"],
            ["0", ".", "⌫", "="]]

    def __init__(self, theme: Theme) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.display = QLineEdit()
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setReadOnly(False)
        font = QFont("Consolas")
        font.setPixelSize(22)
        self.display.setFont(font)
        lay.addWidget(self.display)
        self.answer = QLabel(" ")
        self.answer.setObjectName("dim")
        lay.addWidget(self.answer)

        grid = QGridLayout()
        grid.setSpacing(6)
        for r, row in enumerate(self.KEYS):
            for c, key in enumerate(row):
                b = QPushButton(key)
                b.setMinimumHeight(38)
                b.clicked.connect(lambda _=False, k=key: self.press(k))
                if key == "=":
                    b.setObjectName("op")
                grid.addWidget(b, r, c)
        lay.addLayout(grid)
        self.display.returnPressed.connect(lambda: self.press("="))

    def press(self, key: str) -> None:
        expr = self.display.text()
        if key == "C":
            self.display.clear()
            self.answer.setText(" ")
            return
        if key == "⌫":
            self.display.setText(expr[:-1])
            return
        if key == "=":
            self.display.setText(self.evaluate(expr))
            return
        self.display.setText(expr + key)

    def evaluate(self, expr: str) -> str:
        """Evaluate arithmetic safely — no eval(), no imports, no surprises.

        A calculator that can be talked into running `__import__('os').system(...)` is a
        hole in an assistant that already has hands on the machine, so the expression is
        parsed with `ast` and only numbers and the four operators are allowed.
        """
        import ast
        import operator

        ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Pow: operator.pow,
               ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}

        def walk(node):
            if isinstance(node, ast.Expression):
                return walk(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in ops:
                return ops[type(node.op)](walk(node.left), walk(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
                return ops[type(node.op)](walk(node.operand))
            raise ValueError("only numbers and + - * / ( ) are allowed")

        text = (expr or "").replace("×", "*").replace("÷", "/").replace("^", "**")
        try:
            value = walk(ast.parse(text, mode="eval"))
        except ZeroDivisionError:
            return "cannot divide by zero"
        except Exception:                                       # noqa: BLE001
            return ""
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10g}" if isinstance(value, float) else str(value)


class _Files(QWidget):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        start = str(Path.home())
        self.model.setRootPath(start)
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(start))
        for col in (1, 2, 3):
            self.tree.setColumnHidden(col, True)
        self.tree.setHeaderHidden(True)
        self.tree.doubleClicked.connect(self._open)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.where = QLabel(start)
        self.where.setObjectName("dim")
        row.addWidget(self.where, 1)
        up = QPushButton("Home")
        up.clicked.connect(lambda: self._go(str(Path.home())))
        row.addWidget(up)
        lay.addLayout(row)
        self.tree.clicked.connect(
            lambda idx: self.where.setText(self.model.filePath(idx)))

    def _go(self, folder: str) -> None:
        self.tree.setRootIndex(self.model.index(folder))
        self.where.setText(folder)

    def _open(self, index) -> None:
        path = self.model.filePath(index)
        if Path(path).is_dir():
            self._go(path)
            return
        # Through quiet.py, like every other spawn in this app: a file opened from the
        # dock must not flash a console window either.
        if os.name == "nt":
            os.startfile(path)                                  # noqa: S606
        else:
            quiet.popen(["xdg-open", path])


class _Processes(QWidget):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("what is using this machine")
        self.title.setObjectName("dim")
        lay.addWidget(self.title)
        self.lines = QPlainTextEdit()
        self.lines.setReadOnly(True)
        lay.addWidget(self.lines, 1)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)
        row.addStretch(1)
        lay.addLayout(row)
        # NOT refreshed here. Enumerating every process on Windows takes 0.2 s on an idle
        # machine and seconds behind antivirus — and this widget is built while the deck
        # is being constructed. The list is filled the first time TASK MGR is opened, on a
        # worker (see refresh()).
        self.lines.setPlainText("open TASK MGR to read the process list")

    @staticmethod
    def _read_processes(limit: int = 14):
        """The slow half: returns [(cpu, ram_mb, name)] sorted by CPU. Worker thread only."""
        import psutil
        rows = []
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem = info.get("memory_info")
                rows.append((float(info.get("cpu_percent") or 0),
                             (mem.rss / 1e6) if mem else 0.0,
                             str(info.get("name") or "?")))
            except Exception:                                    # noqa: BLE001
                continue
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        return rows[:limit], len(rows)

    def refresh(self) -> None:
        """Read the process list WITHOUT freezing the deck.

        The report: *"task click pana process aaga matiku, appadiyae hang aagi nikkithu"*.
        `psutil.process_iter` over a Windows process table, on the thread that draws the
        deck, is exactly that: the click is accepted, the panel says nothing, and the whole
        magic screen is frozen until the enumeration finishes. It is 0.2 s on a quiet
        laptop and much longer on a busy one — the click always looked ignored.
        """
        from .. import uiwork
        if getattr(self, "_reading", False):
            return
        self._reading = True
        self.refresh_btn.setEnabled(False)
        self.title.setText("reading the process list… (the deck stays usable)")

        def work(_cancel):
            return self._read_processes()

        def done(result):
            self._reading = False
            self.refresh_btn.setEnabled(True)
            rows, total = result
            body = "\n".join(f"{cpu:5.1f}%  {ram:7.0f} MB  {name}" for cpu, ram, name in rows)
            self.lines.setPlainText(body or "nothing to show")
            self.title.setText(f"top {len(rows)} of {total} by CPU · read just now")

        def failed(text: str) -> None:
            self._reading = False
            self.refresh_btn.setEnabled(True)
            self.lines.setPlainText(f"could not read the process list ({text})")
            self.title.setText("the process list could not be read")

        uiwork.run(work, done=done, failed=failed, name="arc-dock-processes")


class AppDock(QWidget):
    """The panel that holds the in-JARVIS apps. `open(kind)` shows one."""

    ORDER = ("notepad", "calc", "files", "processes")
    TITLES = {"notepad": "NOTEPAD", "calc": "CALCULATOR",
              "files": "FILES", "processes": "TASK MANAGER"}

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dock")
        self.setStyleSheet(_qss(theme))
        self._theme = theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.title = QLabel("NOTEPAD")
        self.title.setObjectName("dockTitle")
        head.addWidget(self.title, 1)
        close = QPushButton("✕")
        close.setFixedSize(26, 24)
        close.setToolTip("Close this panel (Esc)")
        close.clicked.connect(self.close_panel)
        head.addWidget(close)
        lay.addLayout(head)

        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        for kind in self.ORDER:
            self._pages[kind] = self._build(kind)
            self.stack.addWidget(self._pages[kind])
        lay.addWidget(self.stack, 1)
        self.hide()

    def _build(self, kind: str) -> QWidget:
        if kind == "notepad":
            return _Notepad(self._theme)
        if kind == "calc":
            return _Calc(self._theme)
        if kind == "files":
            return _Files(self._theme)
        return _Processes(self._theme)

    # ------------------------------------------------------------------ api
    def open(self, kind: str) -> None:
        kind = (kind or "").strip().lower()
        if kind not in self._pages:
            return
        self.title.setText(self.TITLES.get(kind, kind.upper()))
        self.stack.setCurrentWidget(self._pages[kind])
        if kind == "processes":
            self._pages[kind].refresh()
        self.show()
        self.raise_()

    def close_panel(self) -> None:
        self.hide()

    def is_open(self) -> bool:
        return self.isVisible()
