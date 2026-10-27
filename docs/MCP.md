# MCP — the skills ARC can pick up without new code

Model Context Protocol is how a tool-using assistant borrows someone else's hands.
Arc Desk ships **no** MCP code of its own: it speaks the wire protocol to servers
you install, so a new capability is a config line, not a release.

`MCP.md` is the reference. `python tools\doctor.py` and Settings → Tools both show
the live state.

---

## 1. How it is wired

```
user phrase ──► agent ──► tool schema list ──► model picks mcp__fetch__fetch
                                                     │
                                    arcdesk/ai/mcp.py│  JSON-RPC over stdio
                                                     ▼
                                        npx / uvx  →  server process
```

* Server config lives in `settings.json` under `mcp.servers`.
* Every server tool appears to the model as `mcp__<server>__<tool>`, so it can
  never be confused with a built-in.
* Servers start lazily and are stopped when the app quits — no orphan `node`
  processes in your Task Manager.
* `mcp_servers` is a built-in tool, so you can ask *"what plugins do I have?"*

```jsonc
"mcp": {
  "enabled": true,
  "servers": [
    {"name": "fetch", "command": "uvx", "args": ["mcp-server-fetch"], "enabled": true}
  ]
}
```

---

## 2. One-click presets (all free, no account)

| Preset | Runner | What it gives ARC | Why it matters here |
|---|---|---|---|
| **Fetch** | `uvx mcp-server-fetch` | fetches a URL and returns readable text | closes ARC's biggest gap: `web_search` can open a tab but cannot read it |
| **Time** | `uvx mcp-server-time` | timezone maths | *"3 pm IST in Berlin"* |
| **Memory** | `npx @modelcontextprotocol/server-memory` | a knowledge graph that survives restarts | longer-term notes than one text file |
| **Filesystem** | `npx …server-filesystem` | read/write inside one folder you choose | scoped by design, not your whole drive |
| **Sequential Thinking** | `npx …server-sequential-thinking` | a scratchpad for multi-step problems | helps small local models plan |
| **Git** | `uvx mcp-server-git` | history, diffs, status of a repo | read-only unless you add write flags |
| **GitHub** | `npx @modelcontextprotocol/server-github` | issues, PRs, search | needs a token → marked `needs_account`, never auto-enabled |
| **Playwright** | `npx @playwright/mcp` | real browser control | heavier; off by default |
| **SQLite** | `uvx mcp-server-sqlite` | query a `.db` file | read-only by default |

Button: **Settings → Tools → "Add all free servers"**. It checks the runner first,
so it never adds a row that cannot start, and it tells you what is missing:

```
npx missing — install Node.js LTS, or: winget install OpenJS.NodeJS.LTS
uvx missing — pip install uv
```

---

## 3. What was verified in this environment

Measured with `python tests/test_mcp_presets.py` and a live `MCPManager` start:

| Check | Result |
|---|---|
| Presets defined | 9 (7 free + 2 account-gated) |
| Runner detection | correct — missing `npx`/`uvx` is reported, not crashed on |
| Config round-trip (`enable_all` → `settings.json` → reload) | ✅ |
| Tool name prefixing (`mcp__server__tool`) | ✅ |
| Server lifecycle (start, `initialize`, `tools/list`, `stop`) | ✅ against a stub JSON-RPC server in the test |
| **A real third-party server** | not installed in this sandbox (no Node/npm) — first thing to check on your PC |

That last row is the honest one. The plumbing is tested end to end against a stub
that speaks the same protocol; the specific upstream packages are not vendored and
were not downloaded here, because ARC must never ship someone else's code.

---

## 4. Safety rules that do not bend

1. **Free only.** A preset that needs a paid account is listed, disabled, and marked.
2. **Scoped filesystem.** The Filesystem server gets one folder you pick — never `C:\`.
3. **No auto-install.** Nothing is downloaded until you press a button.
4. **Run from your machine.** The tool result comes back as text through the same
   1 500-character cap as every built-in tool, so a hostile server cannot inject a
   wall of text into the prompt.
5. **Off means off.** `"enabled": false` or `MCP OFF` in the console stops the
   processes; the schema list drops to the built-ins immediately.

---

## 5. Adding a server by hand

Any command that speaks MCP over stdio works:

```
name: myserver
command: python
args: -m my_mcp_server --flag
```

Then: `python tools\doctor.py` → it lists configured servers, whether the command
resolves, and the tool count it reported.

**Related:** [`DO_ANYTHING.md`](DO_ANYTHING.md) (the 26 built-in tools),
[`CAPABILITIES.md`](CAPABILITIES.md) (measured inventory), [`CREDITS.md`](CREDITS.md).
