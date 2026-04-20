"""TCP broker server. Cross-platform (Windows/Linux/macOS) via localhost TCP."""
from __future__ import annotations

import logging
import os
import socket
import threading
import traceback
from typing import Callable

from .paths import broker_pid_file, broker_port_file
from .protocol import Request, Response, decode, encode

log = logging.getLogger(__name__)

Handler = Callable[[dict], object]


class BrokerServer:
    def __init__(
        self,
        handlers: dict[str, Handler],
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self.handlers = handlers
        self.host = host
        self._requested_port = port
        self.port: int = 0
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self._requested_port))
        self._sock.listen(64)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        broker_port_file().write_text(str(self.port))
        broker_pid_file().write_text(str(os.getpid()))
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        for f in (broker_port_file(), broker_pid_file()):
            try:
                f.unlink()
            except FileNotFoundError:
                pass

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            ).start()

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            line, _, _ = buf.partition(b"\n")
            req = decode(line + b"\n")
            if not isinstance(req, Request):
                rsp = Response(ok=False, error="expected request")
            else:
                handler = self.handlers.get(req.op)
                if handler is None:
                    rsp = Response(ok=False, error=f"unknown op: {req.op}")
                else:
                    try:
                        result = handler(req.args)
                        rsp = Response(ok=True, data=result)
                    except Exception as e:
                        log.exception("handler error for %s", req.op)
                        rsp = Response(ok=False, error=f"{type(e).__name__}: {e}")
            conn.sendall(encode(rsp))
        except Exception:
            log.debug("connection error:\n%s", traceback.format_exc())
        finally:
            try:
                conn.close()
            except Exception:
                pass
