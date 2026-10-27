"""MCP (Model Context Protocol) client — plug any open-source tool server into JARVIS.

MCP is the open standard (spec + SDKs on GitHub) that lets an assistant talk to
independent tool servers over JSON-RPC. Adding it here means Arc Desk supports
*any* MCP server without knowing what it is in advance:

    npx -y @modelcontextprotocol/server-filesystem C:\\Users\\you\\Docs
    npx -y @modelcontextprotocol/server-github
    uvx mcp-server-fetch
    python my_own_tool.py --mcp

Each server is spawned as a child process, its tools are listed, and they are
given to the model with an `mcp:<server>:<tool>` name. Nothing is bundled: the
user chooses which GitHub projects to trust, and can delete them any time.

Safety choices:
  * servers are spawn-on-demand and killed on shutdown or crash
  * a server must be listed in settings by the user — we auto-start nothing
  * every call is timeout-bounded (no hanging the agent thread)
  * output is truncated before it reaches the model
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from .. import quiet
import threading
import time

PROTOCOL_VERSION = "2024-11-05"
CALL_TIMEOUT = 30.0
START_TIMEOUT = 12.0


class MCPError(RuntimeError):
    pass


class MCPServer:
    """One stdio MCP server: a child process speaking newline-delimited JSON-RPC."""

    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict | None = None) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.proc: subprocess.Popen | None = None
        self.tools: list[dict] = []
        self.last_error = ""
        self._id = 0
        self._lock = threading.Lock()
        self._buf = ""
        self._responses: dict[int, dict] = {}

    # -- lifecycle -------------------------------------------------------
    def _resolve(self) -> list[str]:
        cmd = self.command
        exe = shutil.which(cmd)
        if exe:
            return [exe, *self.args]
        if cmd in ("npx", "uvx", "uv"):
            # Windows: these are often .cmd/.bat wrappers
            for cand in (f"{cmd}.cmd", f"{cmd}.bat", f"{cmd}.exe"):
                found = shutil.which(cand)
                if found:
                    return [found, *self.args]
        return [cmd, *self.args]

    def start(self) -> bool:
        if self.proc is not None and self.proc.poll() is None:
            return True
        argv = self._resolve()
        try:
            kwargs: dict = {}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            self.proc = quiet.popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
                env={**os.environ, **self.env}, **kwargs)
        except Exception as exc:
            self.last_error = f"cannot start {self.name}: {type(exc).__name__}: {exc}"
            return False

        threading.Thread(target=self._reader, daemon=True,
                         name=f"mcp-{self.name}-out").start()
        threading.Thread(target=self._drain_stderr, daemon=True,
                         name=f"mcp-{self.name}-err").start()
        try:
            self._initialize()
            self.refresh_tools()
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop()
            return False

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # -- transport -------------------------------------------------------
    def _reader(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if isinstance(msg, dict) and "id" in msg:
                self._responses[int(msg["id"])] = msg

    def _drain_stderr(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        for _line in proc.stderr:
            pass

    def _send(self, payload: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise MCPError("server is not running")
        with self._lock:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()

    def _request(self, method: str, params: dict | None = None,
                 timeout: float = CALL_TIMEOUT) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self._responses.pop(rid, None)
            if msg is not None:
                if "error" in msg:
                    raise MCPError(str(msg["error"].get("message") or msg["error"]))
                return msg.get("result") or {}
            if not self.alive:
                raise MCPError(f"{self.name} exited unexpectedly")
            time.sleep(0.02)
        raise MCPError(f"{self.name}: timeout on {method}")

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # -- protocol --------------------------------------------------------
    def _initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "ArcDesk", "version": "0.3"},
        }, timeout=START_TIMEOUT)
        self._notify("notifications/initialized")

    def refresh_tools(self) -> list[dict]:
        try:
            result = self._request("tools/list", timeout=START_TIMEOUT)
        except MCPError as exc:
            self.last_error = str(exc)
            self.tools = []
            return []
        self.tools = list(result.get("tools") or [])
        return self.tools

    def call(self, tool: str, arguments: dict) -> str:
        try:
            result = self._request("tools/call",
                                   {"name": tool, "arguments": arguments or {}})
        except MCPError as exc:
            return f"ERROR: {exc}"
        parts: list[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif item.get("type") == "resource":
                    parts.append(str(item.get("resource", ""))[:400])
        text = "\n".join(p for p in parts if p).strip()
        if not text:
            text = json.dumps(result)[:800]
        return text[:1500]


class MCPManager:
    """Owns every configured server and exposes their tools to the agent."""

    def __init__(self) -> None:
        self.servers: dict[str, MCPServer] = {}
        self.errors: list[str] = []

    # -- config ----------------------------------------------------------
    def load(self, entries: list[dict]) -> None:
        for entry in entries or []:
            if not entry.get("enabled", True):
                continue
            name = str(entry.get("name") or "").strip()
            cmd = str(entry.get("command") or "").strip()
            if not name or not cmd:
                continue
            args = entry.get("args") or []
            if isinstance(args, str):
                args = args.split()
            self.servers[name] = MCPServer(name, cmd, [str(a) for a in args],
                                           entry.get("env") or {})

    def start_all(self) -> list[str]:
        started = []
        for name, srv in self.servers.items():
            if srv.start():
                started.append(f"{name}: {len(srv.tools)} tool(s)")
            else:
                self.errors.append(f"{name}: {srv.last_error}")
        return started

    def stop_all(self) -> None:
        for srv in self.servers.values():
            srv.stop()
        self.servers.clear()

    # -- tool surface ----------------------------------------------------
    def tool_schemas(self, prefix: str = "mcp") -> list[dict]:
        out = []
        for name, srv in self.servers.items():
            for tool in srv.tools:
                tname = tool.get("name") or "tool"
                schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
                if not isinstance(schema, dict):
                    schema = {"type": "object", "properties": {}}
                schema.setdefault("type", "object")
                schema.setdefault("properties", {})
                out.append({
                    "type": "function",
                    "function": {
                        "name": f"{prefix}__{name}__{tname}".replace("-", "_")[:64],
                        "description": (str(tool.get("description") or
                                            f"{tname} from the {name} MCP server"))[:400],
                        "parameters": schema,
                    },
                })
        return out

    def route(self, name: str) -> tuple[MCPServer, str] | None:
        parts = name.split("__")
        if len(parts) < 3 or parts[0] != "mcp":
            return None
        srv = self.servers.get(parts[1])
        if srv is None:
            return None
        return srv, "__".join(parts[2:])

    def call(self, name: str, arguments: dict) -> str:
        hit = self.route(name)
        if hit is None:
            return f"ERROR: no MCP server serves {name}"
        srv, tool = hit
        if not srv.alive:
            srv.start()
        # tool names inside a server may contain underscores we replaced; try both
        candidates = [t.get("name") for t in srv.tools if t.get("name")]
        actual = tool
        if actual not in candidates:
            for c in candidates:
                if c and c.replace("-", "_") == tool:
                    actual = c
                    break
        return srv.call(str(actual), arguments)

    def describe(self) -> str:
        if not self.servers:
            return "no MCP servers configured"
        bits = []
        for name, srv in self.servers.items():
            state = "up" if srv.alive else "down"
            bits.append(f"{name}({state}, {len(srv.tools)} tools)")
        return ", ".join(bits)


# -- convenience: a tiny built-in server so MCP can be tested with no internet
SELFTEST_SERVER = r'''
import json, sys
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
            "serverInfo": {"name": "arc-selftest", "version": "1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
            "name": "echo", "description": "Echo text back",
            "inputSchema": {"type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"]}}]}})
    elif method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}]}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
'''


def write_selftest_server(path) -> None:
    path.write_text(SELFTEST_SERVER, "utf-8")
