"""Inside an app — controls, not just window titles.

Two ways in, tried in this order because each covers what the other cannot:

  1. **Accessibility tree** (Windows UIAutomation, macOS AX, Linux AT-SPI). Fast,
     exact, knows the button's *name* and whether it is enabled — but only works if
     the app publishes an accessible tree.
  2. **Pixels** (`vision.click_text`). Works on anything a camera could read,
     including games, canvases, remote desktops and apps with no accessibility at
     all — but needs the thing to have visible text.

So `click("Send")` asks the accessibility tree first and falls back to the screen.
That combination is what makes "click the blue button in Photoshop" honest: the
general case is the pixels, the fast case is the tree, and whichever fails says why.

Windows is done through PowerShell + `UIAutomationClient` (no pywin32, no wheel, no
install). macOS through `osascript`. Linux: AT-SPI if `pyatspi` happens to be there,
otherwise straight to pixels — and it says so.
"""
from __future__ import annotations

import subprocess

from . import quiet
import sys

from . import vision

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

MAX_CONTROLS = 60


def _run(cmd, timeout: float = 12.0) -> str:
    try:
        out = quiet.run(cmd, capture_output=True, text=True, timeout=timeout,
                             errors="replace")
        return ((out.stdout or "").strip() or (out.stderr or "").strip())[:1500]
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _ps(script: str, timeout: float = 15.0) -> str:
    if not IS_WIN:
        return ""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", script], timeout=timeout)


# ------------------------------------------------------------------ Windows
_WIN_LIST = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [Windows.Automation.AutomationElement]::FocusedElement
while ($root -ne $null -and $root.Current.ControlType.ProgrammaticName -ne 'ControlType.Window') {
    $w = [Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($root)
    if ($w -eq $null) { break }
    $root = $w
}
if ($root -eq $null) { $root = [Windows.Automation.AutomationElement]::RootElement }
$all = $root.FindAll([Windows.Automation.TreeScope]::Descendants,
                     [Windows.Automation.Condition]::TrueCondition)
$n = 0
foreach ($e in $all) {
    $name = $e.Current.Name
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    $type = $e.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
    if ($type -notin @('Button','MenuItem','Edit','Hyperlink','CheckBox','RadioButton',
                       'ComboBox','ListItem','TabItem','Text','Slider','SplitButton')) { continue }
    "$type`t$name`t$($e.Current.IsEnabled)"
    $n++
    if ($n -ge %LIMIT%) { break }
}
"""

_WIN_FIND = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$name = '%NAME%'
$scope = [Windows.Automation.AutomationElement]::RootElement
$cond = New-Object Windows.Automation.PropertyCondition(
            [Windows.Automation.AutomationElement]::NameProperty, $name)
$el = $scope.FindFirst([Windows.Automation.TreeScope]::Descendants, $cond)
if ($el -eq $null) {
    $cond2 = New-Object Windows.Automation.PropertyCondition(
                [Windows.Automation.AutomationElement]::AutomationIdProperty, $name)
    $el = $scope.FindFirst([Windows.Automation.TreeScope]::Descendants, $cond2)
}
if ($el -eq $null) { 'NOTFOUND'; exit 0 }
%ACTION%
"""

_INVOKE = r"""
$p = $null
if ($el.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$p)) {
    $p.Invoke(); 'invoked via InvokePattern'; exit 0
}
if ($el.TryGetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern, [ref]$p)) {
    $p.Select(); 'selected via SelectionItemPattern'; exit 0
}
if ($el.TryGetCurrentPattern([Windows.Automation.TogglePattern]::Pattern, [ref]$p)) {
    $p.Toggle(); 'toggled'; exit 0
}
$pt = $el.GetClickablePoint()
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class M{
[DllImport("user32.dll")]public static extern bool SetCursorPos(int x,int y);
[DllImport("user32.dll")]public static extern void mouse_event(uint f,uint x,uint y,uint d,int e);}'
[M]::SetCursorPos([int]$pt.X, [int]$pt.Y);
[M]::mouse_event(0x2,0,0,0,0); [M]::mouse_event(0x4,0,0,0,0);
"clicked at $($pt.X),$($pt.Y)"
"""

_SET_VALUE = r"""
$vp = $null
if ($el.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) {
    $vp.SetValue('%VALUE%'); 'value set'; exit 0
}
'NOTSUPPORTED'
"""


def _win_list(limit: int) -> str:
    return _ps(_WIN_LIST.replace("%LIMIT%", str(int(limit))), timeout=25)


def _win_find_action(name: str, action: str, value: str = "") -> str:
    safe = name.replace("'", "''")
    body = {"click": _INVOKE,
            "set": _SET_VALUE.replace("%VALUE%", (value or "").replace("'", "''")),
            "focus": "try { $el.SetFocus(); 'focused' } catch { 'NOTSUPPORTED' }"}.get(action, _INVOKE)
    out = _ps(_WIN_FIND.replace("%NAME%", safe).replace("%ACTION%", body), timeout=25)
    return out


# ------------------------------------------------------------------ macOS
def _mac_list(limit: int) -> str:
    script = ('tell application "System Events" to tell (first process whose frontmost is true) '
              'to get {name, role} of every UI element of window 1')
    return _run(["osascript", "-e", script], timeout=15)


def _mac_action(name: str, action: str, value: str = "") -> str:
    safe = name.replace('"', '\\"')
    if action == "set":
        script = (f'tell application "System Events" to tell (first process whose frontmost is true) '
                  f'to set value of text field 1 of window 1 to "{value}"')
    elif action == "focus":
        script = (f'tell application "System Events" to tell (first process whose frontmost is true) '
                  f'to set focused of (first UI element of window 1 whose name is "{safe}") to true')
    else:
        script = (f'tell application "System Events" to tell (first process whose frontmost is true) '
                  f'to click (first UI element of window 1 whose name is "{safe}")')
    return _run(["osascript", "-e", script], timeout=15)


# ------------------------------------------------------------------ Linux
def _linux_available() -> bool:
    try:
        __import__("pyatspi")
        return True
    except Exception:
        return False


def _linux_list(limit: int) -> str:
    if not _linux_available():
        return ("NO_TREE")            # caller falls back to pixels
    try:
        pyatspi = __import__("pyatspi")
        rows = []
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            try:
                for win in app:
                    for child in win:
                        name = child.name or ""
                        if not name:
                            continue
                        rows.append(f"{child.getRoleName()}\t{name}\tTrue")
                        if len(rows) >= limit:
                            return "\n".join(rows)
            except Exception:
                continue
        return "\n".join(rows) or "NO_TREE"
    except Exception:
        return "NO_TREE"


def _linux_action(name: str, action: str, value: str = "") -> str:
    if not _linux_available():
        return "NO_TREE"
    try:
        pyatspi = __import__("pyatspi")
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            for win in app:
                for child in win:
                    if (child.name or "").strip().lower() == name.strip().lower():
                        if action == "set":
                            try:
                                child.queryEditableText().setTextContents(value or "")
                                return "value set"
                            except Exception:
                                return "NOTSUPPORTED"
                        try:
                            child.queryAction().doAction(0)
                            return "invoked"
                        except Exception:
                            return "NOTSUPPORTED"
        return "NOTFOUND"
    except Exception:
        return "NO_TREE"


# ------------------------------------------------------------------ public
def controls(limit: int = 40) -> str:
    """Accessible controls of the focused window — what can be clicked or typed into."""
    limit = max(1, min(int(limit or 40), MAX_CONTROLS))
    out = (_win_list if IS_WIN else _mac_list if IS_MAC else _linux_list)(limit)
    if not out:
        return ("ERROR: could not read the accessibility tree. On Windows make sure "
                "PowerShell is available.")
    if out == "NO_TREE":
        return ("no accessibility tree on this system (install pyatspi on Linux). "
                "I can still read the screen with OCR — ask me to list screen text.")
    return out[:2000]


def _fallback(name: str, action: str, value: str) -> str:
    if action in ("click", "focus") and not value:
        got = vision.click_text(name)
        if not got.lower().startswith("error"):
            return got + "  (found by reading the screen, not the accessibility tree)"
        return got
    return "ERROR: this action needs the accessibility tree, and there is none here"


def act(name: str, action: str = "click", value: str = "") -> str:
    """click / set / focus a control by its visible (or accessible) name."""
    name = (name or "").strip()
    if not name:
        return "ERROR: which control? Give me the visible label."
    action = (action or "click").lower()
    if action not in ("click", "set", "focus"):
        return f"ERROR: unknown action '{action}' (click, set, focus)"
    if action == "set" and not value:
        return "ERROR: 'set' needs a value"

    if IS_WIN:
        out = _win_find_action(name, action, value)
    elif IS_MAC:
        out = _mac_action(name, action, value)
    else:
        out = _linux_action(name, action, value)

    if out in ("NOTFOUND", "NO_TREE", ""):
        return _fallback(name, action, value)
    if "NOTSUPPORTED" in out:
        return _fallback(name, action, value)
    return out


def click(name: str) -> str:
    return act(name, "click")


def set_value(name: str, value: str) -> str:
    return act(name, "set", value)
