"""Broker client used by hooks and MCP server."""
from __future__ import annotations

import socket

from .paths import broker_port_file
from .protocol import Request, Response, decode, encode


class BrokerUnavailable(Exception):
    pass


class BrokerClient:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None, timeout: float = 3.0):
        self.host = host
        self.timeout = timeout
        if port is None:
            pf = broker_port_file()
            if not pf.exists():
                raise BrokerUnavailable("broker.port not found — broker not running?")
            port = int(pf.read_text().strip())
        self.port = port

    def call(self, req: Request) -> Response:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
            s.sendall(encode(req))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                return Response(ok=False, error="empty response from broker")
            return decode(buf)
