"""Newline-delimited JSON protocol for broker TCP socket."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    op: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    ok: bool
    data: Any | None = None
    error: str | None = None


def encode(msg: Request | Response) -> bytes:
    if isinstance(msg, Request):
        payload = {"kind": "req", "op": msg.op, "args": msg.args}
    else:
        payload = {"kind": "rsp", "ok": msg.ok, "data": msg.data, "error": msg.error}
    return (json.dumps(payload) + "\n").encode("utf-8")


def decode(wire: bytes) -> Request | Response:
    s = wire.rstrip(b"\n").decode("utf-8")
    obj = json.loads(s)
    if obj.get("kind") == "req":
        return Request(op=obj["op"], args=obj.get("args") or {})
    return Response(ok=obj["ok"], data=obj.get("data"), error=obj.get("error"))
