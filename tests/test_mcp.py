"""MCP integration test — no internet, no npx, no API key.

Spawns a tiny local MCP server (stdio JSON-RPC), does the real handshake,
lists its tools, calls one, and then checks the agent can see and route it.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_mcp.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import os
import tempfile

# keep tests away from the real settings folder (see config.data_dir)
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.mcp import MCPManager, write_selftest_server  # noqa: E402


def main() -> int:
    server_py = Path(__file__).parent / "_selftest_mcp.py"
    write_selftest_server(server_py)

    mgr = MCPManager()
    mgr.load([{"name": "selftest", "command": sys.executable,
               "args": [str(server_py)], "enabled": True}])
    started = mgr.start_all()
    print("started :", started or mgr.errors)

    schemas = mgr.tool_schemas()
    print("schemas :", [s["function"]["name"] for s in schemas])

    tools.bind_mcp(mgr)
    total = [s["function"]["name"] for s in tools.schemas()]
    routed = [n for n in total if n.startswith("mcp__")]
    print("visible to agent:", len(total), "tools,", len(routed), "from MCP")

    out = tools.call("mcp__selftest__echo", {"text": "hello arc"})
    print("tool result:", out)

    # a dead server must fail cleanly, never raise into the agent loop
    bad = tools.call("mcp__ghost__nope", {})
    print("unknown server:", bad)

    mgr.stop_all()
    ok = (len(routed) == 1 and "echo: hello arc" in out
          and bad.startswith("ERROR"))
    try:
        server_py.unlink()
    except Exception:
        pass
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
