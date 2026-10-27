"""Free MCP servers Arc Desk can add with one click.

Every preset here is free, needs no account, and is an official or first-party
implementation. Anything that needs a token or a subscription is either marked
`needs_account=True` (and left disabled) or not listed at all.

The runner is checked before a preset is enabled, so "Add all" never produces a
row that cannot start: if `npx` is missing, the Node-based servers are skipped
with a reason instead of failing at first use.

Config shape (what MCPManager reads):

    {"name": "fetch", "command": "npx", "args": ["-y", "@.../server-fetch"],
     "env": {}, "enabled": true}
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    repo: str
    command: str
    args: tuple[str, ...] = ()
    needs: str = ""              # executable that must exist on PATH
    env: dict = field(default_factory=dict)
    needs_account: bool = False
    needs_path: bool = False     # needs a folder argument (filesystem)
    needs_repo: bool = False     # needs a git repository to point at
    note: str = ""


# Verified against github.com/modelcontextprotocol/servers (7 reference servers
# remain active upstream) plus first-party Microsoft and GitHub servers.
PRESETS: tuple[Preset, ...] = (
    # These three are Python servers upstream. Their npm names are either absent
    # or held by npm's security placeholder (mcp-server-fetch@0.0.1-security), so
    # npx silently fails. Verified correct runner: uvx.
    Preset("fetch", "Fetch", "modelcontextprotocol/servers",
           "uvx", ("mcp-server-fetch",), "uvx",
           note="read a web page and hand the text to the model — fills JARVIS's "
                "biggest gap (search results it cannot read)"),
    Preset("time", "Time", "modelcontextprotocol/servers",
           "uvx", ("mcp-server-time",), "uvx",
           note="timezone maths, so 'meeting at 3pm IST in Berlin' works"),
    Preset("memory", "Memory", "modelcontextprotocol/servers",
           "npx", ("-y", "@modelcontextprotocol/server-memory"), "npx",
           note="a knowledge graph that survives restarts"),
    Preset("git", "Git", "modelcontextprotocol/servers",
           "uvx", ("mcp-server-git",), "uvx", needs_repo=True,
           note="read history and diffs of a repo (read-only by default)"),
    Preset("sequentialthinking", "Sequential Thinking",
           "modelcontextprotocol/servers",
           "npx", ("-y", "@modelcontextprotocol/server-sequential-thinking"), "npx",
           note="gives the model a scratchpad for multi-step problems"),
    Preset("filesystem", "Filesystem", "modelcontextprotocol/servers",
           "npx", ("-y", "@modelcontextprotocol/server-filesystem"), "npx",
           needs_path=True,
           note="scoped file access — you name the folder, it cannot leave it"),
    Preset("everything", "Everything", "modelcontextprotocol/servers",
           "npx", ("-y", "@modelcontextprotocol/server-everything"), "npx",
           note="the reference test server: proves the MCP link works"),
    Preset("playwright", "Playwright", "microsoft/playwright-mcp",
           "npx", ("-y", "@playwright/mcp"), "npx",
           note="a real browser: click, type, screenshot, read the DOM"),
    Preset("github", "GitHub", "github/github-mcp-server",
           "npx", ("-y", "@modelcontextprotocol/server-github"), "npx",
           env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""}, needs_account=True,
           note="issues and PRs — needs a free GitHub token, so it stays off until "
                "you add one"),
)


def by_key(key: str) -> Preset | None:
    return next((p for p in PRESETS if p.key == key), None)


def runner_ok(p: Preset) -> bool:
    return bool(shutil.which(p.needs)) if p.needs else True


def available() -> list[Preset]:
    """Runnable and account-free — what "Add all" would actually enable."""
    return [p for p in PRESETS if runner_ok(p) and not p.needs_account]


def missing_runners() -> list[str]:
    seen: dict[str, str] = {}
    for p in PRESETS:
        if p.needs and not runner_ok(p) and p.needs not in seen:
            seen[p.needs] = p.name
    return [f"{exe} (needed by {name})" for exe, name in seen.items()]


def _repo_dir() -> str:
    """Arc Desk's own folder, when it is a git checkout."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    return str(root) if (root / ".git").exists() else ""


def default_servers(include_account: bool = False,
                    workspace: str = "") -> list[dict]:
    """The list to write into cfg["mcp"]["servers"] — safe, free, runnable."""
    out: list[dict] = []
    for p in PRESETS:
        if p.needs_account and not include_account:
            continue
        if not runner_ok(p):
            continue
        args = list(p.args)
        if p.needs_path:
            if not workspace:
                continue                      # no folder chosen yet: skip, don't guess
            args.append(workspace)
        if p.needs_repo:
            repo = _repo_dir()
            if not repo:
                continue
            args += ["--repository", repo]
        out.append({"name": p.key, "command": p.command, "args": args,
                    "env": dict(p.env), "enabled": True})
    return out


def enable_all(cfg: dict, workspace: str = "") -> tuple[list[str], list[str]]:
    """Merge the runnable presets into cfg. Returns (added, skipped-with-reason)."""
    added: list[str] = []
    skipped: list[str] = []
    mcp = cfg.setdefault("mcp", {})
    servers = mcp.setdefault("servers", [])
    have = {str(s.get("name")) for s in servers if isinstance(s, dict)}

    for p in PRESETS:
        if p.key in have:
            continue
        if p.needs_account:
            skipped.append(f"{p.name} (needs a GitHub token)")
            continue
        if not runner_ok(p):
            skipped.append(f"{p.name} (needs {p.needs})")
            continue
        args = list(p.args)
        if p.needs_path:
            if not workspace:
                skipped.append(f"{p.name} (choose a folder first)")
                continue
            args.append(workspace)
        if p.needs_repo:
            repo = _repo_dir()
            if not repo:
                skipped.append(f"{p.name} (needs a git repository to read)")
                continue
            args += ["--repository", repo]
        servers.append({"name": p.key, "command": p.command, "args": args,
                        "env": dict(p.env), "enabled": True})
        added.append(p.name)

    mcp["enabled"] = True
    return added, skipped


def describe() -> str:
    """One-line summary for the console and the settings note."""
    ok = available()
    if not ok:
        need = ", ".join(missing_runners()) or "npx"
        return f"no MCP server can start yet — install Node.js (for {need})"
    names = ", ".join(p.name for p in ok)
    return f"{len(ok)} free servers ready: {names}"
