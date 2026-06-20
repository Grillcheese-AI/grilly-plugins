"""Standalone broker entry point: `python -m broker`.

Used by hooks (later) that need a persistent shared store across sessions. The
MCP server (mcpd/server.py) embeds a broker directly, so this is optional for
the minimal slice — but it gives a long-lived process hooks can connect to.

Singleton: if a broker is already answering on the recorded port, exit quietly.
"""
from __future__ import annotations

import os
import signal
import sys
import time

from .client import BrokerClient
from .handlers import build_handlers
from .paths import broker_port_file
from .protocol import Request
from .server import BrokerServer


def _already_running() -> bool:
    if not broker_port_file().exists():
        return False
    try:
        rsp = BrokerClient(timeout=1.0).call(Request(op="ping"))
        return bool(rsp.ok)
    except Exception:
        return False


def main() -> int:
    if _already_running():
        print("elephant-coder2 broker already running", file=sys.stderr)
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    store, handlers = build_handlers(root)
    srv = BrokerServer(handlers=handlers)
    srv.start()
    print(f"elephant-coder2 broker on 127.0.0.1:{srv.port} (project={root})", file=sys.stderr)

    stop = {"flag": False}

    def _shutdown(*_):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop["flag"]:
            time.sleep(0.5)
    finally:
        srv.stop()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
