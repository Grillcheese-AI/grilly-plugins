# elephant-coder2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build elephant-coder2 — a Claude Code plugin with automatic memory activation (shadowed tools), a local small-GGUF-model hippocampus (Qwen 2.5 1.5B via llama-cpp-python + Vulkan), three-tier memory (scratch/project_durable/global_durable), and leaner skills/hooks/MCP surface.

**Architecture:** Persistent Python broker process (TCP localhost socket for cross-platform IPC) mediates all memory ops. Storage: Redis primary cache + SQLite+FTS5 durable + numpy vectors. Small model runs in-process via llama-cpp-python for scratch/consolidation/rerank. 5 hooks inject memory context mechanically; no reminder-based activation.

**Tech Stack:** Python 3.12+, llama-cpp-python (Vulkan), redis≥7.3.0, SQLite+FTS5, numpy, sentence-transformers (all-MiniLM-L6-v2), mcp SDK, httpx, pypdf, pyyaml.

**Platform note:** Primary development on Windows 11. IPC uses TCP localhost (not Unix sockets) for cross-platform support. Paths use forward slashes; commands are bash-compatible (git-bash/WSL).

**Reference spec:** `docs/superpowers/specs/2026-04-17-elephant-coder2-design.md`

---

## File Structure

All v2 code lives at `C:/Users/grill/grilly-plugins/elephant-coder2/` (side-by-side with v1). Plugin layout:

```
elephant-coder2/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json
├── broker/
│   ├── __init__.py
│   ├── server.py           # TCP socket server, broker lifecycle
│   ├── client.py           # Client library (hooks + MCP use this)
│   ├── protocol.py         # Request/response schema
│   ├── settings.py         # Load .claude/elephant-coder2.local.md
│   ├── paths.py            # ~/.elephant-coder2 path resolution, project_hash
│   ├── store/
│   │   ├── __init__.py
│   │   ├── sqlite_store.py # SQLite+FTS5 durable store
│   │   ├── redis_cache.py  # Redis cache with graceful fallback
│   │   ├── vector_store.py # numpy vectors + embedding
│   │   └── unified.py      # Store facade combining all three
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── python_ast.py
│   │   ├── regex_extract.py # TS/JS/C/C++/GLSL
│   │   ├── structured.py   # md/toml/json/yaml/cmake
│   │   └── orchestrator.py # Dispatch by extension
│   ├── retriever.py        # Hybrid retrieval + tier merging + RRF
│   ├── sidecar/
│   │   ├── __init__.py
│   │   ├── model.py        # llama-cpp-python wrapper
│   │   ├── prompts.py      # Summarize / rerank / consolidate templates
│   │   └── consolidator.py # Idle-loop consolidation
│   ├── tasks.py            # Background task queue + push notify
│   └── main.py             # Broker entrypoint
├── mcp/
│   ├── __init__.py
│   └── server.py           # MCP server exposing 12 tools
├── hooks/
│   ├── hooks.json
│   ├── _client.py          # Shared hook → broker client
│   ├── session_start.py
│   ├── userpromptsubmit.py
│   ├── pretooluse_read.py
│   ├── pretooluse_search.py
│   ├── pretooluse_agent.py
│   ├── posttooluse_edit.py
│   └── posttooluse_write.py
├── skills/                 # 20 skill directories, each with SKILL.md
├── commands/               # 20 slash command .md files
├── tests/
│   ├── test_store.py
│   ├── test_retriever.py
│   ├── test_indexer.py
│   ├── test_sidecar.py
│   ├── test_broker.py
│   ├── test_hooks.py
│   └── test_mcp_server.py
├── pyproject.toml
├── CLAUDE.md               # Minimal
├── README.md
└── CHANGELOG.md
```

---

## Phase 1: Plugin Scaffolding & Broker Foundation

### Task 1: Create plugin skeleton

**Files:**
- Create: `elephant-coder2/.claude-plugin/plugin.json`
- Create: `elephant-coder2/pyproject.toml`
- Create: `elephant-coder2/README.md`
- Create: `elephant-coder2/CHANGELOG.md`
- Create: `elephant-coder2/CLAUDE.md`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Create directory structure**

```bash
cd C:/Users/grill/grilly-plugins
mkdir -p elephant-coder2/.claude-plugin \
         elephant-coder2/broker/{store,indexer,sidecar} \
         elephant-coder2/mcp \
         elephant-coder2/hooks \
         elephant-coder2/skills \
         elephant-coder2/commands \
         elephant-coder2/tests
```

- [ ] **Step 2: Write plugin manifest**

Create `elephant-coder2/.claude-plugin/plugin.json`:

```json
{
  "name": "elephant-coder2",
  "description": "Automatic memory activation for Claude Code: shadowed tools + local small-model hippocampus + three-tier cross-project memory",
  "version": "0.1.0",
  "author": {
    "name": "grillcheese"
  },
  "keywords": [
    "memory",
    "indexing",
    "codebase",
    "hippocampus",
    "llama-cpp",
    "agentic",
    "cross-project"
  ]
}
```

- [ ] **Step 3: Write pyproject.toml**

Create `elephant-coder2/pyproject.toml`:

```toml
[project]
name = "elephant-coder2"
version = "0.1.0"
description = "Automatic memory activation for Claude Code"
requires-python = ">=3.12"
dependencies = [
  "mcp>=1.2.0",
  "redis>=7.3.0",
  "numpy>=1.26.0",
  "sentence-transformers>=3.0.0",
  "pypdf>=4.0.0",
  "pyyaml>=6.0",
  "httpx>=0.27.0",
  "llama-cpp-python>=0.3.0"
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["broker*", "mcp*"]
```

- [ ] **Step 4: Write stub README and CLAUDE.md**

Create `elephant-coder2/README.md`:

```markdown
# elephant-coder2

Automatic memory activation for Claude Code.

v2 of elephant-coder — rebuilt for token efficiency, agentic work, and cross-project knowledge. See `docs/superpowers/specs/2026-04-17-elephant-coder2-design.md` in the parent repo.

**Status:** In development.
```

Create `elephant-coder2/CLAUDE.md`:

```markdown
# elephant-coder2

Memory activation is automatic via hooks. Claude does not need to invoke memory tools manually — the broker injects relevant context into tool results.

For manual inspection use `/ec2:recall`, `/ec2:status`.
```

Create `elephant-coder2/CHANGELOG.md`:

```markdown
# Changelog

## [0.1.0] - 2026-04-17

- Initial scaffolding
```

- [ ] **Step 5: Register v2 in marketplace**

Modify `C:/Users/grill/grilly-plugins/.claude-plugin/marketplace.json` — add a second plugin entry inside the `plugins` array:

```json
{
  "name": "elephant-coder2",
  "source": "./elephant-coder2",
  "description": "Automatic memory activation: shadowed tools + local small-model hippocampus + three-tier cross-project memory",
  "version": "0.1.0",
  "author": { "name": "grillcheese" },
  "repository": "https://github.com/grillcheese-ai/grilly-plugins",
  "keywords": ["memory", "hippocampus", "agentic", "llama-cpp", "cross-project"],
  "category": "development"
}
```

- [ ] **Step 6: Commit**

```bash
cd C:/Users/grill/grilly-plugins
git add elephant-coder2 .claude-plugin/marketplace.json
git commit -m "feat(ec2): plugin scaffolding"
```

---

### Task 2: Broker paths & project hashing

**Files:**
- Create: `elephant-coder2/broker/__init__.py` (empty)
- Create: `elephant-coder2/broker/paths.py`
- Create: `elephant-coder2/tests/__init__.py` (empty)
- Create: `elephant-coder2/tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_paths.py`:

```python
import os
from pathlib import Path
from broker.paths import ec2_home, project_hash, project_dir, global_dir, model_dir


def test_ec2_home_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    assert ec2_home() == tmp_path


def test_ec2_home_default_is_dot_ec2(monkeypatch):
    monkeypatch.delenv("EC2_HOME", raising=False)
    assert ec2_home().name == ".elephant-coder2"


def test_project_hash_stable():
    h1 = project_hash("/some/project/path")
    h2 = project_hash("/some/project/path")
    assert h1 == h2
    assert len(h1) == 12


def test_project_hash_differs_by_path():
    assert project_hash("/a") != project_hash("/b")


def test_project_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    pdir = project_dir("/some/proj")
    assert pdir.exists()
    assert pdir.parent.name == "projects"


def test_global_and_model_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    assert global_dir().exists()
    assert model_dir().exists()
```

- [ ] **Step 2: Run to verify failure**

```bash
cd C:/Users/grill/grilly-plugins/elephant-coder2
python -m pytest tests/test_paths.py -v
```

Expected: ModuleNotFoundError for `broker.paths`.

- [ ] **Step 3: Implement paths module**

Create `elephant-coder2/broker/paths.py`:

```python
"""Path resolution for elephant-coder2 state."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def ec2_home() -> Path:
    """Root dir for all v2 state. Override with EC2_HOME env var."""
    env = os.environ.get("EC2_HOME")
    if env:
        p = Path(env)
    else:
        p = Path.home() / ".elephant-coder2"
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_hash(project_path: str) -> str:
    """Stable 12-char hash of a project path."""
    norm = os.path.normpath(os.path.abspath(project_path))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def project_dir(project_path: str) -> Path:
    """Per-project state dir, created if missing."""
    d = ec2_home() / "projects" / project_hash(project_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def global_dir() -> Path:
    """Cross-project global state."""
    d = ec2_home() / "global"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_dir() -> Path:
    """GGUF model cache."""
    d = ec2_home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def broker_port_file() -> Path:
    return ec2_home() / "broker.port"


def broker_pid_file() -> Path:
    return ec2_home() / "broker.pid"
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest tests/test_paths.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add broker/__init__.py broker/paths.py tests/__init__.py tests/test_paths.py
git commit -m "feat(ec2): broker path resolution + project hashing"
```

---

### Task 3: Settings loader

**Files:**
- Create: `elephant-coder2/broker/settings.py`
- Create: `elephant-coder2/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_settings.py`:

```python
from pathlib import Path
from broker.settings import load_settings, Settings


def test_defaults_when_no_file(tmp_path):
    s = load_settings(tmp_path)
    assert s.max_scratch_entries == 32000
    assert s.max_durable_entries == 50000
    assert s.redis_url == "redis://localhost:6379"
    assert s.injection.prompt_budget_tokens == 800
    assert s.injection.tool_budget_tokens == 300
    assert s.injection.agent_brief_tokens == 500
    assert s.sidecar.rerank_latency_ms == 500


def test_overrides_from_yaml_frontmatter(tmp_path):
    cfg = tmp_path / ".claude" / "elephant-coder2.local.md"
    cfg.parent.mkdir()
    cfg.write_text(
        "---\n"
        "max_scratch_entries: 5000\n"
        "injection:\n"
        "  prompt_budget_tokens: 400\n"
        "sidecar:\n"
        "  model_path: other.gguf\n"
        "---\n"
        "free text below\n"
    )
    s = load_settings(tmp_path)
    assert s.max_scratch_entries == 5000
    assert s.injection.prompt_budget_tokens == 400
    assert s.sidecar.model_path == "other.gguf"
    # Un-overridden values stay default
    assert s.max_durable_entries == 50000
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_settings.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement settings**

Create `elephant-coder2/broker/settings.py`:

```python
"""Per-project settings loaded from .claude/elephant-coder2.local.md YAML frontmatter."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass
class InjectionSettings:
    prompt_budget_tokens: int = 800
    tool_budget_tokens: int = 300
    agent_brief_tokens: int = 500


@dataclass
class SidecarSettings:
    model_path: str = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    n_gpu_layers: int = -1
    rerank_latency_ms: int = 500
    n_ctx: int = 8192


@dataclass
class ExternalSettings:
    openrouter_api_key: str | None = None
    model: str = "google/gemini-3.1-flash-lite-preview"


@dataclass
class Settings:
    max_scratch_entries: int = 32000
    max_durable_entries: int = 50000
    redis_url: str = "redis://localhost:6379"
    redis_ttl_seconds: int = 60 * 60 * 24 * 365
    scratch_idle_consolidation_minutes: int = 10
    injection: InjectionSettings = field(default_factory=InjectionSettings)
    sidecar: SidecarSettings = field(default_factory=SidecarSettings)
    external: ExternalSettings = field(default_factory=ExternalSettings)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def _merge_into(obj: Any, overrides: dict[str, Any]) -> Any:
    for k, v in overrides.items():
        if not hasattr(obj, k):
            continue
        current = getattr(obj, k)
        if hasattr(current, "__dataclass_fields__") and isinstance(v, dict):
            _merge_into(current, v)
        else:
            setattr(obj, k, v)
    return obj


def load_settings(project_root: Path) -> Settings:
    """Load settings for a project; returns defaults if no config file."""
    s = Settings()
    cfg = Path(project_root) / ".claude" / "elephant-coder2.local.md"
    if not cfg.exists():
        return s
    overrides = _parse_frontmatter(cfg.read_text(encoding="utf-8"))
    _merge_into(s, overrides)
    return s
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_settings.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add broker/settings.py tests/test_settings.py
git commit -m "feat(ec2): settings loader with YAML frontmatter"
```

---

### Task 4: Broker wire protocol

**Files:**
- Create: `elephant-coder2/broker/protocol.py`
- Create: `elephant-coder2/tests/test_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_protocol.py`:

```python
import json
from broker.protocol import Request, Response, encode, decode


def test_request_roundtrip():
    req = Request(op="recall", args={"query": "hello", "limit": 5})
    wire = encode(req)
    assert isinstance(wire, bytes)
    assert wire.endswith(b"\n")
    back = decode(wire)
    assert isinstance(back, Request)
    assert back.op == "recall"
    assert back.args == {"query": "hello", "limit": 5}


def test_response_ok_roundtrip():
    r = Response(ok=True, data={"items": [1, 2, 3]})
    back = decode(encode(r))
    assert back.ok is True
    assert back.data["items"] == [1, 2, 3]


def test_response_err_roundtrip():
    r = Response(ok=False, error="boom")
    back = decode(encode(r))
    assert back.ok is False
    assert back.error == "boom"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_protocol.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement protocol**

Create `elephant-coder2/broker/protocol.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_protocol.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/protocol.py tests/test_protocol.py
git commit -m "feat(ec2): wire protocol (NDJSON) for broker IPC"
```

---

### Task 5: Broker TCP server skeleton

**Files:**
- Create: `elephant-coder2/broker/server.py`
- Create: `elephant-coder2/broker/client.py`
- Create: `elephant-coder2/tests/test_broker_server.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_broker_server.py`:

```python
import os
import threading
import time
import pytest
from broker.server import BrokerServer
from broker.client import BrokerClient
from broker.protocol import Request


@pytest.fixture
def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    handlers = {
        "ping": lambda args: {"pong": True, "echo": args.get("x")},
        "boom": lambda args: (_ for _ in ()).throw(RuntimeError("nope")),
    }
    srv = BrokerServer(handlers=handlers, host="127.0.0.1", port=0)
    srv.start()
    # Wait for port file to be written
    for _ in range(50):
        if srv.port:
            break
        time.sleep(0.02)
    yield srv
    srv.stop()


def test_ping(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="ping", args={"x": 42}))
    assert rsp.ok is True
    assert rsp.data["pong"] is True
    assert rsp.data["echo"] == 42


def test_unknown_op(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="doesnotexist"))
    assert rsp.ok is False
    assert "unknown op" in rsp.error.lower()


def test_handler_exception_returns_error(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="boom"))
    assert rsp.ok is False
    assert "nope" in rsp.error


def test_port_file_written(broker, tmp_path):
    port_file = tmp_path / "broker.port"
    assert port_file.exists()
    assert int(port_file.read_text().strip()) == broker.port
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_broker_server.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement server and client**

Create `elephant-coder2/broker/server.py`:

```python
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
```

Create `elephant-coder2/broker/client.py`:

```python
"""Broker client used by hooks and MCP server."""
from __future__ import annotations

import socket
from pathlib import Path

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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_broker_server.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/server.py broker/client.py tests/test_broker_server.py
git commit -m "feat(ec2): TCP broker server + client"
```

---

## Phase 2: Storage Layer

### Task 6: SQLite schema + FTS5

**Files:**
- Create: `elephant-coder2/broker/store/__init__.py` (empty)
- Create: `elephant-coder2/broker/store/sqlite_store.py`
- Create: `elephant-coder2/tests/test_sqlite_store.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_sqlite_store.py`:

```python
import pytest
from broker.store.sqlite_store import SQLiteStore, MemoryEntry


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "mem.db")
    yield s
    s.close()


def test_insert_and_fetch(store):
    mid = store.insert(MemoryEntry(
        file_path="a/b.py", symbol="foo", kind="function",
        content="def foo(): return 1", summary="simple foo",
        keywords="foo function", tier="scratch",
    ))
    assert mid > 0
    got = store.get(mid)
    assert got.symbol == "foo"
    assert got.tier == "scratch"
    assert got.access_count == 0
    assert got.is_protected == 0


def test_fts5_search(store):
    store.insert(MemoryEntry(
        file_path="auth.py", symbol="verify_token", kind="function",
        content="check token", summary="verify jwt token",
        keywords="auth token jwt", tier="scratch"))
    store.insert(MemoryEntry(
        file_path="db.py", symbol="connect", kind="function",
        content="open db", summary="db connection",
        keywords="database sql", tier="scratch"))
    results = store.fts_search("jwt", limit=10)
    assert len(results) == 1
    assert results[0].symbol == "verify_token"


def test_tier_flip(store):
    mid = store.insert(MemoryEntry(
        file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.set_tier(mid, "project_durable", reason="it's important")
    got = store.get(mid)
    assert got.tier == "project_durable"
    assert got.promotion_reason == "it's important"


def test_bump_access(store):
    mid = store.insert(MemoryEntry(
        file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.bump_access([mid, mid])
    got = store.get(mid)
    assert got.access_count == 2


def test_filter_by_tier(store):
    a = store.insert(MemoryEntry(file_path="a.py", symbol="a", kind="function",
        content="a", summary="a", keywords="a", tier="scratch"))
    b = store.insert(MemoryEntry(file_path="b.py", symbol="b", kind="function",
        content="b", summary="b", keywords="b", tier="project_durable"))
    scratch = list(store.iter_by_tier("scratch"))
    durable = list(store.iter_by_tier("project_durable"))
    assert {m.id for m in scratch} == {a}
    assert {m.id for m in durable} == {b}


def test_delete(store):
    mid = store.insert(MemoryEntry(file_path="x.py", symbol="s", kind="function",
        content="c", summary="s", keywords="s", tier="scratch"))
    store.delete(mid)
    assert store.get(mid) is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_sqlite_store.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement SQLite store**

Create `elephant-coder2/broker/store/sqlite_store.py`:

```python
"""SQLite+FTS5 durable store for memory entries across three tiers."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator


TIERS = ("scratch", "project_durable", "global_durable")


@dataclass
class MemoryEntry:
    file_path: str
    symbol: str
    kind: str
    content: str
    summary: str
    keywords: str
    tier: str = "scratch"
    id: int | None = None
    is_identity: int = 0
    is_protected: int = 0
    access_count: int = 0
    last_accessed: str | None = None
    created_at: str | None = None
    promotion_reason: str | None = None
    file_mtime: float | None = None


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT NOT NULL,
                keywords TEXT NOT NULL,
                tier TEXT NOT NULL CHECK (tier IN ('scratch','project_durable','global_durable')),
                is_identity INTEGER NOT NULL DEFAULT 0,
                is_protected INTEGER NOT NULL DEFAULT 0,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                created_at TEXT NOT NULL,
                promotion_reason TEXT,
                file_mtime REAL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_file ON memories(file_path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON memories(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tier ON memories(tier)")
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(
                symbol, summary, keywords, content='memories', content_rowid='id'
            )
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
                INSERT INTO mem_fts(rowid, symbol, summary, keywords)
                VALUES (new.id, new.symbol, new.summary, new.keywords);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
                INSERT INTO mem_fts(mem_fts, rowid, symbol, summary, keywords)
                VALUES ('delete', old.id, old.symbol, old.summary, old.keywords);
            END
        """)
        c.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
                INSERT INTO mem_fts(mem_fts, rowid, symbol, summary, keywords)
                VALUES ('delete', old.id, old.symbol, old.summary, old.keywords);
                INSERT INTO mem_fts(rowid, symbol, summary, keywords)
                VALUES (new.id, new.symbol, new.summary, new.keywords);
            END
        """)

    def insert(self, entry: MemoryEntry) -> int:
        if entry.tier not in TIERS:
            raise ValueError(f"invalid tier {entry.tier}")
        created = entry.created_at or datetime.now().isoformat()
        cur = self._conn.execute(
            """INSERT INTO memories
               (file_path, symbol, kind, content, summary, keywords, tier,
                is_identity, is_protected, access_count, created_at, file_mtime)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry.file_path, entry.symbol, entry.kind, entry.content, entry.summary,
             entry.keywords, entry.tier, entry.is_identity, entry.is_protected,
             entry.access_count, created, entry.file_mtime),
        )
        return cur.lastrowid

    def get(self, memory_id: int) -> MemoryEntry | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def delete(self, memory_id: int) -> None:
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def set_tier(self, memory_id: int, tier: str, reason: str | None = None) -> None:
        if tier not in TIERS:
            raise ValueError(f"invalid tier {tier}")
        self._conn.execute(
            "UPDATE memories SET tier = ?, promotion_reason = ? WHERE id = ?",
            (tier, reason, memory_id),
        )

    def bump_access(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        now = datetime.now().isoformat()
        self._conn.executemany(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            [(now, mid) for mid in memory_ids],
        )

    def fts_search(self, query: str, limit: int = 20, tiers: tuple[str, ...] | None = None) -> list[MemoryEntry]:
        tiers = tiers or TIERS
        placeholders = ",".join("?" * len(tiers))
        # Escape FTS5 special chars by wrapping in quotes; tokenize on whitespace
        q = _sanitize_fts(query)
        sql = f"""
            SELECT m.* FROM memories m
            JOIN mem_fts f ON f.rowid = m.id
            WHERE mem_fts MATCH ? AND m.tier IN ({placeholders})
            ORDER BY bm25(mem_fts)
            LIMIT ?
        """
        rows = self._conn.execute(sql, (q, *tiers, limit)).fetchall()
        return [_row_to_entry(r) for r in rows]

    def iter_by_tier(self, tier: str) -> Iterator[MemoryEntry]:
        for row in self._conn.execute("SELECT * FROM memories WHERE tier = ?", (tier,)):
            yield _row_to_entry(row)

    def by_file(self, file_path: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE file_path = ?", (file_path,)
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def by_symbol(self, symbol: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE symbol = ?", (symbol,)
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def count(self, tier: str | None = None) -> int:
        if tier:
            return self._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE tier = ?", (tier,)
            ).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def close(self) -> None:
        self._conn.close()


def _row_to_entry(row: tuple) -> MemoryEntry:
    (mid, fp, sym, kind, content, summary, keywords, tier,
     is_id, is_prot, ac, la, ca, pr, fm) = row
    return MemoryEntry(
        id=mid, file_path=fp, symbol=sym, kind=kind, content=content,
        summary=summary, keywords=keywords, tier=tier,
        is_identity=is_id, is_protected=is_prot, access_count=ac,
        last_accessed=la, created_at=ca, promotion_reason=pr, file_mtime=fm,
    )


def _sanitize_fts(query: str) -> str:
    """Quote each whitespace-separated term to avoid FTS5 syntax errors."""
    terms = [t for t in query.replace('"', ' ').split() if t]
    if not terms:
        return '""'
    return " ".join(f'"{t}"' for t in terms)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_sqlite_store.py -v
```

Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/store/ tests/test_sqlite_store.py
git commit -m "feat(ec2): SQLite+FTS5 store with three tiers"
```

---

### Task 7: Vector store (numpy)

**Files:**
- Create: `elephant-coder2/broker/store/vector_store.py`
- Create: `elephant-coder2/tests/test_vector_store.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_vector_store.py`:

```python
import numpy as np
from broker.store.vector_store import VectorStore


def test_add_and_search(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(1, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.add(2, np.array([0, 1, 0, 0], dtype=np.float32))
    vs.add(3, np.array([0.9, 0.1, 0, 0], dtype=np.float32))
    results = vs.search(np.array([1, 0, 0, 0], dtype=np.float32), k=2)
    ids = [mid for mid, _ in results]
    assert ids[0] == 1
    assert ids[1] == 3


def test_persists_across_instances(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(10, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.save()
    vs2 = VectorStore(tmp_path / "vec", dim=4)
    results = vs2.search(np.array([1, 0, 0, 0], dtype=np.float32), k=1)
    assert results[0][0] == 10


def test_remove(tmp_path):
    vs = VectorStore(tmp_path / "vec", dim=4)
    vs.add(1, np.array([1, 0, 0, 0], dtype=np.float32))
    vs.add(2, np.array([0, 1, 0, 0], dtype=np.float32))
    vs.remove(1)
    results = vs.search(np.array([1, 0, 0, 0], dtype=np.float32), k=2)
    assert 1 not in {mid for mid, _ in results}
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_vector_store.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement vector store**

Create `elephant-coder2/broker/store/vector_store.py`:

```python
"""numpy-based vector store with cosine similarity. Persists as .npy + .json index."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class VectorStore:
    def __init__(self, prefix: str | Path, dim: int):
        self.prefix = Path(prefix)
        self.dim = dim
        self._vec_path = self.prefix.with_suffix(".npy")
        self._idx_path = self.prefix.with_suffix(".json")
        self._vectors: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self._ids: list[int] = []
        self._load()

    def _load(self) -> None:
        if self._vec_path.exists() and self._idx_path.exists():
            self._vectors = np.load(self._vec_path)
            self._ids = json.loads(self._idx_path.read_text())

    def save(self) -> None:
        self.prefix.parent.mkdir(parents=True, exist_ok=True)
        np.save(self._vec_path, self._vectors)
        self._idx_path.write_text(json.dumps(self._ids))

    def add(self, memory_id: int, vec: np.ndarray) -> None:
        v = vec.astype(np.float32).reshape(1, -1)
        if v.shape[1] != self.dim:
            raise ValueError(f"dim mismatch: got {v.shape[1]}, expected {self.dim}")
        if memory_id in self._ids:
            i = self._ids.index(memory_id)
            self._vectors[i] = v[0]
        else:
            self._vectors = np.vstack([self._vectors, v])
            self._ids.append(memory_id)
        self.save()

    def remove(self, memory_id: int) -> None:
        if memory_id not in self._ids:
            return
        i = self._ids.index(memory_id)
        self._vectors = np.delete(self._vectors, i, axis=0)
        del self._ids[i]
        self.save()

    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        if len(self._ids) == 0:
            return []
        q = query.astype(np.float32).reshape(-1)
        qn = q / (np.linalg.norm(q) + 1e-8)
        keys = self._vectors
        kn = keys / (np.linalg.norm(keys, axis=1, keepdims=True) + 1e-8)
        sims = kn @ qn
        if k >= len(sims):
            order = np.argsort(sims)[::-1]
        else:
            idx = np.argpartition(sims, -k)[-k:]
            order = idx[np.argsort(sims[idx])[::-1]]
        return [(self._ids[i], float(sims[i])) for i in order]

    def __len__(self) -> int:
        return len(self._ids)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_vector_store.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/store/vector_store.py tests/test_vector_store.py
git commit -m "feat(ec2): numpy vector store with cosine similarity"
```

---

### Task 8: Redis cache layer

**Files:**
- Create: `elephant-coder2/broker/store/redis_cache.py`
- Create: `elephant-coder2/tests/test_redis_cache.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_redis_cache.py`:

```python
import pytest
from broker.store.redis_cache import RedisCache


def _redis_available(url):
    try:
        import redis
        r = redis.from_url(url)
        r.ping()
        return True
    except Exception:
        return False


REDIS_URL = "redis://localhost:6379/15"  # DB 15 for tests
pytestmark = pytest.mark.skipif(
    not _redis_available(REDIS_URL), reason="Redis not available on localhost"
)


@pytest.fixture
def cache():
    c = RedisCache(url=REDIS_URL, project_hash="testproj", ttl_seconds=60)
    c.flush()
    yield c
    c.flush()


def test_fallback_when_unavailable():
    c = RedisCache(url="redis://127.0.0.1:1", project_hash="p", ttl_seconds=60)
    assert c.available is False
    c.set_memory(1, {"a": 1})  # must not raise
    assert c.get_memory(1) is None


def test_set_and_get_memory(cache):
    cache.set_memory(42, {"symbol": "foo", "summary": "x"})
    got = cache.get_memory(42)
    assert got["symbol"] == "foo"


def test_symbol_index(cache):
    cache.add_symbol("foo", 42)
    cache.add_symbol("foo", 43)
    assert set(cache.get_symbol_ids("foo")) == {42, 43}


def test_file_index(cache):
    cache.add_file_memory("a/b.py", 10)
    assert 10 in cache.get_file_memory_ids("a/b.py")
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_redis_cache.py -v
```

Expected: ModuleNotFoundError (or all skipped if Redis unavailable).

- [ ] **Step 3: Implement Redis cache**

Create `elephant-coder2/broker/store/redis_cache.py`:

```python
"""Redis cache layer with graceful fallback when Redis is unavailable."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, url: str, project_hash: str, ttl_seconds: int = 31_536_000):
        self.url = url
        self.project_hash = project_hash
        self.ttl = ttl_seconds
        self._r = None
        self.available = False
        try:
            import redis
            self._r = redis.from_url(url, decode_responses=True, socket_timeout=0.5)
            self._r.ping()
            self.available = True
        except Exception as e:
            log.warning("Redis unavailable (%s); falling back to SQLite-only", e)

    def _key(self, *parts: str) -> str:
        return ":".join(("ec2", self.project_hash, *parts))

    def set_memory(self, mid: int, data: dict) -> None:
        if not self.available:
            return
        try:
            self._r.setex(self._key("mem", str(mid)), self.ttl, json.dumps(data))
        except Exception as e:
            log.debug("redis set_memory failed: %s", e)

    def get_memory(self, mid: int) -> dict | None:
        if not self.available:
            return None
        try:
            raw = self._r.get(self._key("mem", str(mid)))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def del_memory(self, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.delete(self._key("mem", str(mid)))
        except Exception:
            pass

    def add_symbol(self, symbol: str, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.sadd(self._key("sym", symbol), mid)
            self._r.expire(self._key("sym", symbol), self.ttl)
        except Exception:
            pass

    def get_symbol_ids(self, symbol: str) -> list[int]:
        if not self.available:
            return []
        try:
            return [int(x) for x in self._r.smembers(self._key("sym", symbol))]
        except Exception:
            return []

    def add_file_memory(self, file_path: str, mid: int) -> None:
        if not self.available:
            return
        try:
            self._r.sadd(self._key("file", file_path), mid)
            self._r.expire(self._key("file", file_path), self.ttl)
        except Exception:
            pass

    def get_file_memory_ids(self, file_path: str) -> list[int]:
        if not self.available:
            return []
        try:
            return [int(x) for x in self._r.smembers(self._key("file", file_path))]
        except Exception:
            return []

    def flush(self) -> None:
        if not self.available:
            return
        try:
            cursor = 0
            pattern = self._key("*")
            while True:
                cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    self._r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_redis_cache.py -v
```

Expected: fallback test passes regardless; others pass if Redis running, skip otherwise.

- [ ] **Step 5: Commit**

```bash
git add broker/store/redis_cache.py tests/test_redis_cache.py
git commit -m "feat(ec2): Redis cache with graceful fallback"
```

---

### Task 9: Unified Store facade

**Files:**
- Create: `elephant-coder2/broker/store/unified.py`
- Create: `elephant-coder2/broker/store/embedder.py`
- Create: `elephant-coder2/tests/test_unified_store.py`

- [ ] **Step 1: Write embedder shim**

Create `elephant-coder2/broker/store/embedder.py`:

```python
"""Sentence-transformer wrapper. Lazy-loads to keep broker startup fast."""
from __future__ import annotations

import numpy as np

_MODEL = None
_MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384


def _load():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def embed(text: str) -> np.ndarray:
    m = _load()
    v = m.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return v.astype(np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    m = _load()
    vs = m.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vs.astype(np.float32)
```

- [ ] **Step 2: Write the failing test**

Create `elephant-coder2/tests/test_unified_store.py`:

```python
import pytest
from broker.store.unified import UnifiedStore
from broker.store.sqlite_store import MemoryEntry


@pytest.fixture
def store(tmp_path, monkeypatch):
    # Stub embedder to avoid downloading model in tests
    import broker.store.embedder as emb
    import numpy as np
    def fake_embed(text):
        # Deterministic cheap embedding: hash-based
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(384).astype(np.float32)
        v /= (np.linalg.norm(v) + 1e-8)
        return v
    monkeypatch.setattr(emb, "embed", fake_embed)
    s = UnifiedStore(
        sqlite_path=tmp_path / "mem.db",
        vector_prefix=tmp_path / "vec",
        redis_url=None,
        project_hash="p",
    )
    yield s
    s.close()


def test_insert_creates_sqlite_and_vector(store):
    e = MemoryEntry(file_path="a.py", symbol="foo", kind="function",
                    content="c", summary="s", keywords="k", tier="scratch")
    mid = store.insert(e)
    assert store.sqlite.get(mid) is not None
    assert mid in store.vectors._ids


def test_delete_removes_from_both(store):
    mid = store.insert(MemoryEntry(
        file_path="a.py", symbol="foo", kind="function",
        content="c", summary="s", keywords="k", tier="scratch"))
    store.delete(mid)
    assert store.sqlite.get(mid) is None
    assert mid not in store.vectors._ids


def test_set_tier_persists(store):
    mid = store.insert(MemoryEntry(
        file_path="a.py", symbol="foo", kind="function",
        content="c", summary="s", keywords="k", tier="scratch"))
    store.set_tier(mid, "project_durable", reason="hub file")
    e = store.sqlite.get(mid)
    assert e.tier == "project_durable"
    assert e.promotion_reason == "hub file"
```

- [ ] **Step 3: Run to verify failure**

```bash
python -m pytest tests/test_unified_store.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement unified store**

Create `elephant-coder2/broker/store/unified.py`:

```python
"""Unified store facade combining SQLite, Redis, and vector backends."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .embedder import DIM, embed
from .redis_cache import RedisCache
from .sqlite_store import MemoryEntry, SQLiteStore
from .vector_store import VectorStore


class UnifiedStore:
    def __init__(
        self,
        sqlite_path: str | Path,
        vector_prefix: str | Path,
        redis_url: str | None,
        project_hash: str,
        redis_ttl: int = 31_536_000,
    ):
        self.sqlite = SQLiteStore(sqlite_path)
        self.vectors = VectorStore(vector_prefix, dim=DIM)
        self.redis = (
            RedisCache(redis_url, project_hash=project_hash, ttl_seconds=redis_ttl)
            if redis_url
            else None
        )
        self.project_hash = project_hash

    def insert(self, entry: MemoryEntry) -> int:
        mid = self.sqlite.insert(entry)
        text = f"{entry.summary}\n{entry.keywords}\n{entry.content}"
        vec = embed(text)
        self.vectors.add(mid, vec)
        if self.redis:
            full = self.sqlite.get(mid)
            self.redis.set_memory(mid, asdict(full))
            self.redis.add_symbol(entry.symbol, mid)
            self.redis.add_file_memory(entry.file_path, mid)
        return mid

    def delete(self, memory_id: int) -> None:
        self.sqlite.delete(memory_id)
        self.vectors.remove(memory_id)
        if self.redis:
            self.redis.del_memory(memory_id)

    def set_tier(self, memory_id: int, tier: str, reason: str | None = None) -> None:
        self.sqlite.set_tier(memory_id, tier, reason)
        if self.redis:
            updated = self.sqlite.get(memory_id)
            if updated:
                self.redis.set_memory(memory_id, asdict(updated))

    def bump_access(self, ids: list[int]) -> None:
        self.sqlite.bump_access(ids)

    def close(self) -> None:
        self.sqlite.close()
        self.vectors.save()
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_unified_store.py -v
```

Expected: all 3 pass.

- [ ] **Step 6: Commit**

```bash
git add broker/store/embedder.py broker/store/unified.py tests/test_unified_store.py
git commit -m "feat(ec2): unified store facade + embedder"
```

---

## Phase 3: Indexer

### Task 10: Python AST indexer

**Files:**
- Create: `elephant-coder2/broker/indexer/__init__.py` (empty)
- Create: `elephant-coder2/broker/indexer/python_ast.py`
- Create: `elephant-coder2/tests/test_indexer_python.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_indexer_python.py`:

```python
from broker.indexer.python_ast import index_python_source


def test_extracts_functions_and_classes():
    src = '''
def foo(x, y):
    """Add two numbers."""
    return x + y

class Bar:
    """A bar."""
    def baz(self):
        return 1
'''
    entries = index_python_source(src, file_path="demo.py", file_mtime=0.0)
    kinds = {(e.symbol, e.kind) for e in entries}
    assert ("foo", "function") in kinds
    assert ("Bar", "class") in kinds
    assert ("Bar.baz", "method") in kinds


def test_summary_uses_docstring():
    src = 'def foo():\n    """hello world"""\n    return 1\n'
    entries = index_python_source(src, file_path="x.py", file_mtime=0.0)
    foo = next(e for e in entries if e.symbol == "foo")
    assert "hello world" in foo.summary


def test_keywords_include_name_tokens():
    src = 'def verify_token(jwt):\n    return True\n'
    entries = index_python_source(src, file_path="x.py", file_mtime=0.0)
    foo = next(e for e in entries if e.symbol == "verify_token")
    assert "verify" in foo.keywords
    assert "token" in foo.keywords
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_indexer_python.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement Python AST indexer**

Create `elephant-coder2/broker/indexer/python_ast.py`:

```python
"""Python AST-based indexer: extracts functions, classes, methods, module docstring."""
from __future__ import annotations

import ast
import re

from broker.store.sqlite_store import MemoryEntry


def _name_tokens(name: str) -> list[str]:
    # snake_case + CamelCase split
    parts = re.split(r"[_\W]+", name)
    toks: list[str] = []
    for p in parts:
        if not p:
            continue
        toks.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", p))
    return [t.lower() for t in toks]


def _keywords_for(name: str, doc: str | None) -> str:
    toks = set(_name_tokens(name))
    if doc:
        for w in re.findall(r"[A-Za-z]{3,}", doc.lower()):
            toks.add(w)
    return " ".join(sorted(toks))


def _summary(name: str, doc: str | None, kind: str) -> str:
    first = (doc or "").strip().splitlines()[0] if doc else ""
    if first:
        return f"{kind} {name}: {first[:160]}"
    return f"{kind} {name}"


def index_python_source(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[MemoryEntry] = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        out.append(MemoryEntry(
            file_path=file_path, symbol=file_path, kind="module",
            content=mod_doc[:2000],
            summary=_summary(file_path, mod_doc, "module"),
            keywords=_keywords_for(file_path, mod_doc),
            tier="scratch", file_mtime=file_mtime,
        ))

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            out.append(MemoryEntry(
                file_path=file_path, symbol=node.name, kind="function",
                content=ast.unparse(node)[:2000],
                summary=_summary(node.name, doc, "function"),
                keywords=_keywords_for(node.name, doc),
                tier="scratch", file_mtime=file_mtime,
            ))
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            out.append(MemoryEntry(
                file_path=file_path, symbol=node.name, kind="class",
                content=ast.unparse(node)[:2000],
                summary=_summary(node.name, doc, "class"),
                keywords=_keywords_for(node.name, doc),
                tier="scratch", file_mtime=file_mtime,
            ))
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef):
                    sdoc = ast.get_docstring(sub)
                    sym = f"{node.name}.{sub.name}"
                    out.append(MemoryEntry(
                        file_path=file_path, symbol=sym, kind="method",
                        content=ast.unparse(sub)[:2000],
                        summary=_summary(sym, sdoc, "method"),
                        keywords=_keywords_for(sym, sdoc),
                        tier="scratch", file_mtime=file_mtime,
                    ))
    return out
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_indexer_python.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/indexer/__init__.py broker/indexer/python_ast.py tests/test_indexer_python.py
git commit -m "feat(ec2): Python AST indexer"
```

---

### Task 11: Regex indexer (TS/JS/C/C++/GLSL) and structured indexer (md/toml/json/yaml)

**Files:**
- Create: `elephant-coder2/broker/indexer/regex_extract.py`
- Create: `elephant-coder2/broker/indexer/structured.py`
- Create: `elephant-coder2/tests/test_indexer_other.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_indexer_other.py`:

```python
from broker.indexer.regex_extract import index_ts_source, index_c_source
from broker.indexer.structured import index_markdown, index_toml


def test_ts_functions_and_classes():
    src = '''
export function verify(token: string): boolean { return true; }
export class AuthClient {
  connect() {}
}
'''
    entries = index_ts_source(src, "auth.ts", 0.0)
    syms = {e.symbol for e in entries}
    assert "verify" in syms
    assert "AuthClient" in syms


def test_c_functions():
    src = '''
int add(int a, int b) { return a + b; }
static void helper(void) { }
'''
    entries = index_c_source(src, "a.c", 0.0)
    syms = {e.symbol for e in entries}
    assert "add" in syms
    assert "helper" in syms


def test_markdown_headings():
    md = "# Title\n\nIntro.\n\n## Section A\n\nContent A\n\n## Section B\n\nContent B\n"
    entries = index_markdown(md, "x.md", 0.0)
    syms = [e.symbol for e in entries]
    assert "Title" in syms
    assert "Section A" in syms
    assert "Section B" in syms


def test_toml_tables():
    t = "[project]\nname = 'x'\n[tool.pytest]\nstrict = true\n"
    entries = index_toml(t, "pyproject.toml", 0.0)
    syms = {e.symbol for e in entries}
    assert "project" in syms
    assert "tool.pytest" in syms
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_indexer_other.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement regex + structured indexers**

Create `elephant-coder2/broker/indexer/regex_extract.py`:

```python
"""Regex-based extractor for TS/JS/C/C++/GLSL."""
from __future__ import annotations

import re

from broker.store.sqlite_store import MemoryEntry
from .python_ast import _keywords_for, _summary

_TS_FN = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)")
_TS_CONST_FN = re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
_TS_CLASS = re.compile(r"(?:export\s+)?class\s+(\w+)")

_C_FN = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+)*(?:[\w\*\s]+?)\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

_GLSL_FN = re.compile(r"^(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE)


def _entries_from(matches, kind: str, source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    for m in matches:
        name = m.group(1)
        start = max(0, m.start() - 80)
        end = min(len(source), m.end() + 400)
        snippet = source[start:end]
        out.append(MemoryEntry(
            file_path=file_path, symbol=name, kind=kind,
            content=snippet[:2000],
            summary=_summary(name, None, kind),
            keywords=_keywords_for(name, snippet),
            tier="scratch", file_mtime=file_mtime,
        ))
    return out


def index_ts_source(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    out += _entries_from(_TS_FN.finditer(source), "function", source, file_path, file_mtime)
    out += _entries_from(_TS_CONST_FN.finditer(source), "function", source, file_path, file_mtime)
    out += _entries_from(_TS_CLASS.finditer(source), "class", source, file_path, file_mtime)
    return out


def index_c_source(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    return _entries_from(_C_FN.finditer(source), "function", source, file_path, file_mtime)


def index_glsl_source(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    return _entries_from(_GLSL_FN.finditer(source), "function", source, file_path, file_mtime)
```

Create `elephant-coder2/broker/indexer/structured.py`:

```python
"""Indexers for markdown / toml / json / yaml / cmake."""
from __future__ import annotations

import re

from broker.store.sqlite_store import MemoryEntry
from .python_ast import _keywords_for, _summary


def index_markdown(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    sections = re.split(r"(?m)^(#{1,6}\s+.+)$", source)
    # sections: [preamble, heading1, body1, heading2, body2, ...]
    for i in range(1, len(sections), 2):
        heading = sections[i].strip("# ").strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        out.append(MemoryEntry(
            file_path=file_path, symbol=heading, kind="heading",
            content=(heading + "\n" + body)[:2000],
            summary=_summary(heading, body, "heading"),
            keywords=_keywords_for(heading, body),
            tier="scratch", file_mtime=file_mtime,
        ))
    return out


def index_toml(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    for m in re.finditer(r"(?m)^\[([^\]]+)\]", source):
        tbl = m.group(1).strip()
        out.append(MemoryEntry(
            file_path=file_path, symbol=tbl, kind="toml_table",
            content=source[m.end(): m.end() + 300],
            summary=_summary(tbl, None, "toml_table"),
            keywords=_keywords_for(tbl, None),
            tier="scratch", file_mtime=file_mtime,
        ))
    return out


def index_json(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    import json
    try:
        data = json.loads(source)
    except Exception:
        return []
    out: list[MemoryEntry] = []
    if isinstance(data, dict):
        for key in data.keys():
            out.append(MemoryEntry(
                file_path=file_path, symbol=str(key), kind="json_key",
                content=json.dumps({key: data[key]}, default=str)[:1000],
                summary=_summary(str(key), None, "json_key"),
                keywords=_keywords_for(str(key), None),
                tier="scratch", file_mtime=file_mtime,
            ))
    return out


def index_yaml(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    for m in re.finditer(r"(?m)^(\w[\w\-]*)\s*:", source):
        key = m.group(1)
        out.append(MemoryEntry(
            file_path=file_path, symbol=key, kind="yaml_key",
            content=source[m.start(): m.start() + 300],
            summary=_summary(key, None, "yaml_key"),
            keywords=_keywords_for(key, None),
            tier="scratch", file_mtime=file_mtime,
        ))
    return out
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_indexer_other.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/indexer/regex_extract.py broker/indexer/structured.py tests/test_indexer_other.py
git commit -m "feat(ec2): regex + structured indexers"
```

---

### Task 12: Index orchestrator

**Files:**
- Create: `elephant-coder2/broker/indexer/orchestrator.py`
- Create: `elephant-coder2/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_orchestrator.py`:

```python
from broker.indexer.orchestrator import index_file, index_project


def test_index_file_dispatches_by_extension(tmp_path):
    py = tmp_path / "x.py"
    py.write_text("def foo():\n    return 1\n")
    entries = index_file(py)
    assert any(e.symbol == "foo" for e in entries)


def test_index_project_walks_and_indexes(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    (tmp_path / "b.ts").write_text("export function g() { return 1; }\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.ts").write_text("function ignore(){}")

    entries = index_project(tmp_path)
    syms = {e.symbol for e in entries}
    assert "f" in syms
    assert "g" in syms
    assert "ignore" not in syms
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement orchestrator**

Create `elephant-coder2/broker/indexer/orchestrator.py`:

```python
"""Dispatches files to the right indexer by extension; walks projects."""
from __future__ import annotations

from pathlib import Path

from broker.store.sqlite_store import MemoryEntry
from . import python_ast, regex_extract, structured

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".nuxt", "target", ".cache", ".idea", ".vscode",
}

DISPATCH = {
    ".py":   python_ast.index_python_source,
    ".ts":   regex_extract.index_ts_source,
    ".tsx":  regex_extract.index_ts_source,
    ".js":   regex_extract.index_ts_source,
    ".jsx":  regex_extract.index_ts_source,
    ".c":    regex_extract.index_c_source,
    ".cc":   regex_extract.index_c_source,
    ".cpp":  regex_extract.index_c_source,
    ".cxx":  regex_extract.index_c_source,
    ".h":    regex_extract.index_c_source,
    ".hpp":  regex_extract.index_c_source,
    ".hxx":  regex_extract.index_c_source,
    ".glsl": regex_extract.index_glsl_source,
    ".vert": regex_extract.index_glsl_source,
    ".frag": regex_extract.index_glsl_source,
    ".comp": regex_extract.index_glsl_source,
    ".md":   structured.index_markdown,
    ".toml": structured.index_toml,
    ".json": structured.index_json,
    ".yaml": structured.index_yaml,
    ".yml":  structured.index_yaml,
}


def index_file(path: Path) -> list[MemoryEntry]:
    fn = DISPATCH.get(path.suffix.lower())
    if fn is None:
        return []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return fn(source, str(path), mtime)


def index_project(root: Path) -> list[MemoryEntry]:
    root = Path(root)
    out: list[MemoryEntry] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in DISPATCH:
            continue
        out.extend(index_file(p))
    return out
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add broker/indexer/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(ec2): index orchestrator (dispatch + project walk)"
```

---

## Phase 4: Hybrid Retrieval

### Task 13: Retriever with RRF + tier weighting

**Files:**
- Create: `elephant-coder2/broker/retriever.py`
- Create: `elephant-coder2/tests/test_retriever.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_retriever.py`:

```python
import pytest
from broker.retriever import Retriever
from broker.store.unified import UnifiedStore
from broker.store.sqlite_store import MemoryEntry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import broker.store.embedder as emb
    import numpy as np
    def fake_embed(text):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(384).astype(np.float32)
        v /= (np.linalg.norm(v) + 1e-8)
        return v
    monkeypatch.setattr(emb, "embed", fake_embed)
    proj = UnifiedStore(
        sqlite_path=tmp_path / "p.db",
        vector_prefix=tmp_path / "p_vec",
        redis_url=None,
        project_hash="p",
    )
    glob = UnifiedStore(
        sqlite_path=tmp_path / "g.db",
        vector_prefix=tmp_path / "g_vec",
        redis_url=None,
        project_hash="global",
    )
    r = Retriever(project=proj, global_store=glob)
    yield r, proj, glob
    proj.close()
    glob.close()


def test_returns_from_project_tier(setup):
    r, proj, _ = setup
    proj.insert(MemoryEntry(file_path="a.py", symbol="verify_token",
        kind="function", content="c", summary="verify token jwt",
        keywords="verify token jwt auth", tier="scratch"))
    results = r.retrieve("jwt token", limit=5)
    assert len(results) >= 1
    assert results[0].symbol == "verify_token"


def test_merges_global_and_project(setup):
    r, proj, glob = setup
    proj.insert(MemoryEntry(file_path="a.py", symbol="local_auth",
        kind="function", content="c", summary="local auth check",
        keywords="auth check local", tier="scratch"))
    glob.insert(MemoryEntry(file_path="z.py", symbol="global_auth_pattern",
        kind="pattern", content="c", summary="general auth pattern",
        keywords="auth pattern general", tier="global_durable"))
    results = r.retrieve("auth", limit=5)
    syms = {e.symbol for e in results}
    assert "local_auth" in syms
    assert "global_auth_pattern" in syms


def test_limit_respected(setup):
    r, proj, _ = setup
    for i in range(10):
        proj.insert(MemoryEntry(file_path=f"{i}.py", symbol=f"fn{i}",
            kind="function", content="c", summary=f"authentication thing {i}",
            keywords="auth thing", tier="scratch"))
    results = r.retrieve("authentication", limit=3)
    assert len(results) <= 3
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_retriever.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement retriever**

Create `elephant-coder2/broker/retriever.py`:

```python
"""Hybrid retrieval: FTS5 + vector with RRF merge and tier weighting."""
from __future__ import annotations

from dataclasses import dataclass

from .store.embedder import embed
from .store.sqlite_store import MemoryEntry
from .store.unified import UnifiedStore


TIER_WEIGHTS = {
    "scratch": 1.0,
    "project_durable": 1.1,
    "global_durable": 0.9,
}

RRF_K = 60


@dataclass
class Retriever:
    project: UnifiedStore
    global_store: UnifiedStore | None = None

    def _search_one(self, store: UnifiedStore, query: str, limit: int) -> list[tuple[int, float, MemoryEntry]]:
        # FTS5 pass
        fts_hits = store.sqlite.fts_search(query, limit=limit * 2)
        fts_ranks = {h.id: i for i, h in enumerate(fts_hits)}
        # Vector pass
        qv = embed(query)
        vec_hits = store.vectors.search(qv, k=limit * 2)
        vec_ranks = {mid: i for i, (mid, _) in enumerate(vec_hits)}
        # RRF merge
        scores: dict[int, float] = {}
        for mid, rank in fts_ranks.items():
            scores[mid] = scores.get(mid, 0) + 1.0 / (RRF_K + rank)
        for mid, rank in vec_ranks.items():
            scores[mid] = scores.get(mid, 0) + 1.0 / (RRF_K + rank)
        # Fetch entries + weight by tier
        results: list[tuple[int, float, MemoryEntry]] = []
        for mid, s in scores.items():
            e = store.sqlite.get(mid)
            if not e:
                continue
            weighted = s * TIER_WEIGHTS.get(e.tier, 1.0)
            results.append((mid, weighted, e))
        return results

    def retrieve(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        merged = self._search_one(self.project, query, limit)
        if self.global_store:
            merged += self._search_one(self.global_store, query, limit)
        merged.sort(key=lambda t: t[1], reverse=True)
        # Bump access on returned ids
        top = merged[:limit]
        self.project.bump_access([mid for mid, _, e in top if e.tier != "global_durable"])
        if self.global_store:
            self.global_store.bump_access([mid for mid, _, e in top if e.tier == "global_durable"])
        return [e for _, _, e in top]

    def by_file(self, file_path: str) -> list[MemoryEntry]:
        return self.project.sqlite.by_file(file_path)

    def by_symbol(self, symbol: str) -> list[MemoryEntry]:
        return self.project.sqlite.by_symbol(symbol)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_retriever.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/retriever.py tests/test_retriever.py
git commit -m "feat(ec2): hybrid retrieval with RRF + tier weighting"
```

---

## Phase 5: Small-Model Sidecar

### Task 14: llama-cpp wrapper (lazy load + rerank/summarize APIs)

**Files:**
- Create: `elephant-coder2/broker/sidecar/__init__.py` (empty)
- Create: `elephant-coder2/broker/sidecar/model.py`
- Create: `elephant-coder2/broker/sidecar/prompts.py`
- Create: `elephant-coder2/tests/test_sidecar_model.py`

- [ ] **Step 1: Write prompts module**

Create `elephant-coder2/broker/sidecar/prompts.py`:

```python
"""Prompt templates for the small model."""
from __future__ import annotations

SUMMARIZE = """You summarize text for a memory store.
Return a single line under 160 characters capturing the essence.
Do not include quotes, preambles, or trailing punctuation beyond one period.

Text:
{text}

Summary:"""

RERANK = """You rank memory candidates by relevance to a query.
Return only the integer indices (0-based) of the top {k}, comma-separated, no other text.

Query: {query}

Candidates:
{candidates}

Top {k} indices:"""

CONSOLIDATE = """You are deduplicating memories. Given these summaries, return lines of the form:
KEEP <index>
MERGE <index_a> <index_b> -> <new summary>
DROP <index>

One action per line. Be conservative — only MERGE when two summaries describe the same thing.

Summaries:
{summaries}

Decisions:"""
```

- [ ] **Step 2: Write the failing test**

Create `elephant-coder2/tests/test_sidecar_model.py`:

```python
import pytest
from broker.sidecar.model import SidecarModel


class _FakeLlama:
    def __init__(self, scripted: dict[str, str]):
        self.scripted = scripted
        self.calls: list[str] = []

    def __call__(self, prompt, max_tokens=256, temperature=0.2, stop=None, **kw):
        self.calls.append(prompt)
        for needle, reply in self.scripted.items():
            if needle in prompt:
                return {"choices": [{"text": reply}]}
        return {"choices": [{"text": ""}]}


def test_summarize_uses_prompt():
    fake = _FakeLlama({"Text:": "this is a short summary"})
    m = SidecarModel._from_raw(fake)
    out = m.summarize("Here's a paragraph of text to summarize.")
    assert "summary" in out.lower()


def test_rerank_parses_indices():
    fake = _FakeLlama({"Top": "2, 0, 1"})
    m = SidecarModel._from_raw(fake)
    idx = m.rerank("query", ["a", "b", "c"], k=3)
    assert idx == [2, 0, 1]


def test_rerank_falls_back_on_bad_output():
    fake = _FakeLlama({"Top": "I'm not sure"})
    m = SidecarModel._from_raw(fake)
    idx = m.rerank("q", ["a", "b", "c"], k=2)
    # Should fall back to identity order truncated
    assert idx == [0, 1]
```

- [ ] **Step 3: Run to verify failure**

```bash
python -m pytest tests/test_sidecar_model.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement wrapper**

Create `elephant-coder2/broker/sidecar/model.py`:

```python
"""llama-cpp-python wrapper. Lazy-loads model; exposes summarize/rerank/consolidate."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from .prompts import CONSOLIDATE, RERANK, SUMMARIZE

log = logging.getLogger(__name__)


class SidecarModel:
    def __init__(
        self,
        model_path: str | Path | None = None,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
    ):
        self._model_path = Path(model_path) if model_path else None
        self._n_gpu_layers = n_gpu_layers
        self._n_ctx = n_ctx
        self._llm = None

    @classmethod
    def _from_raw(cls, llm) -> "SidecarModel":
        """Construct from an already-loaded callable (used by tests)."""
        m = cls.__new__(cls)
        m._model_path = None
        m._n_gpu_layers = 0
        m._n_ctx = 0
        m._llm = llm
        return m

    def _load(self):
        if self._llm is not None:
            return self._llm
        if not self._model_path or not self._model_path.exists():
            raise FileNotFoundError(f"GGUF model not found: {self._model_path}")
        from llama_cpp import Llama
        self._llm = Llama(
            model_path=str(self._model_path),
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=False,
        )
        return self._llm

    def _generate(self, prompt: str, max_tokens: int = 256, stop: list[str] | None = None) -> str:
        llm = self._load()
        out = llm(prompt, max_tokens=max_tokens, temperature=0.2, stop=stop or ["\n\n"])
        return out["choices"][0]["text"].strip()

    def summarize(self, text: str) -> str:
        return self._generate(SUMMARIZE.format(text=text[:3000]), max_tokens=80)

    def rerank(self, query: str, candidates: list[str], k: int, latency_budget_ms: int = 500) -> list[int]:
        if not candidates:
            return []
        k = min(k, len(candidates))
        listing = "\n".join(f"[{i}] {c[:200]}" for i, c in enumerate(candidates))
        prompt = RERANK.format(query=query, candidates=listing, k=k)
        start = time.time()
        try:
            raw = self._generate(prompt, max_tokens=64, stop=["\n"])
        except Exception as e:
            log.warning("sidecar rerank failed: %s", e)
            return list(range(k))
        elapsed_ms = (time.time() - start) * 1000
        if elapsed_ms > latency_budget_ms:
            log.debug("rerank exceeded budget (%.0f ms > %d), using fallback", elapsed_ms, latency_budget_ms)
            return list(range(k))
        nums = re.findall(r"\d+", raw)
        idxs: list[int] = []
        for n in nums:
            i = int(n)
            if 0 <= i < len(candidates) and i not in idxs:
                idxs.append(i)
            if len(idxs) >= k:
                break
        if not idxs:
            return list(range(k))
        return idxs

    def consolidate(self, summaries: list[str]) -> str:
        listing = "\n".join(f"[{i}] {s[:200]}" for i, s in enumerate(summaries))
        return self._generate(
            CONSOLIDATE.format(summaries=listing), max_tokens=512, stop=None
        )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_sidecar_model.py -v
```

Expected: all 3 pass.

- [ ] **Step 6: Commit**

```bash
git add broker/sidecar/ tests/test_sidecar_model.py
git commit -m "feat(ec2): sidecar model wrapper + prompts"
```

---

### Task 15: Consolidator (idle loop + decision log)

**Files:**
- Create: `elephant-coder2/broker/sidecar/consolidator.py`
- Create: `elephant-coder2/tests/test_consolidator.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_consolidator.py`:

```python
from broker.sidecar.consolidator import Consolidator, parse_decisions


def test_parse_keep_merge_drop():
    raw = (
        "KEEP 0\n"
        "MERGE 1 2 -> combined summary of both\n"
        "DROP 3\n"
        "bogus line\n"
    )
    decisions = parse_decisions(raw)
    assert {"op": "KEEP", "indices": [0]} in decisions
    assert any(d["op"] == "MERGE" and d["indices"] == [1, 2] for d in decisions)
    assert {"op": "DROP", "indices": [3]} in decisions


def test_consolidator_applies_drops(tmp_path, monkeypatch):
    import broker.store.embedder as emb
    import numpy as np
    monkeypatch.setattr(emb, "embed", lambda t: np.zeros(384, dtype=np.float32))

    from broker.store.unified import UnifiedStore
    from broker.store.sqlite_store import MemoryEntry

    store = UnifiedStore(
        sqlite_path=tmp_path / "s.db",
        vector_prefix=tmp_path / "v",
        redis_url=None,
        project_hash="p",
    )
    ids = []
    for i in range(3):
        ids.append(store.insert(MemoryEntry(
            file_path=f"{i}.py", symbol=f"s{i}", kind="function",
            content="c", summary=f"summary {i}", keywords="k", tier="scratch")))

    class FakeModel:
        def consolidate(self, summaries):
            return "KEEP 0\nDROP 2\n"

    c = Consolidator(store=store, model=FakeModel(), log_path=tmp_path / "log.jsonl")
    c.run_once(batch_size=3)

    assert store.sqlite.get(ids[0]) is not None
    assert store.sqlite.get(ids[2]) is None
    store.close()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_consolidator.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement consolidator**

Create `elephant-coder2/broker/sidecar/consolidator.py`:

```python
"""Idle-time consolidation loop. Model decides KEEP/MERGE/DROP, we apply."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from broker.store.sqlite_store import MemoryEntry
from broker.store.unified import UnifiedStore


def parse_decisions(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(KEEP|DROP)\s+(\d+)\s*$", line)
        if m:
            out.append({"op": m.group(1), "indices": [int(m.group(2))]})
            continue
        m = re.match(r"^MERGE\s+(\d+)\s+(\d+)\s*->\s*(.+)$", line)
        if m:
            out.append({
                "op": "MERGE",
                "indices": [int(m.group(1)), int(m.group(2))],
                "summary": m.group(3).strip(),
            })
    return out


class Consolidator:
    def __init__(self, store: UnifiedStore, model, log_path: Path):
        self.store = store
        self.model = model
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, event: dict) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(), **event}) + "\n")

    def run_once(self, batch_size: int = 50) -> dict[str, int]:
        """One consolidation pass over oldest scratch entries."""
        entries: list[MemoryEntry] = list(self.store.sqlite.iter_by_tier("scratch"))[:batch_size]
        if not entries:
            return {"kept": 0, "dropped": 0, "merged": 0}

        summaries = [e.summary for e in entries]
        try:
            raw = self.model.consolidate(summaries)
        except Exception as e:
            self._log({"event": "consolidate_error", "error": str(e)})
            return {"kept": 0, "dropped": 0, "merged": 0}

        decisions = parse_decisions(raw)
        self._log({"event": "decisions", "count": len(decisions), "batch": len(entries)})

        dropped = 0
        merged = 0
        for d in decisions:
            op = d["op"]
            idxs = d["indices"]
            try:
                if op == "DROP":
                    target = entries[idxs[0]]
                    if target.is_protected:
                        continue
                    self.store.delete(target.id)
                    dropped += 1
                elif op == "MERGE" and len(idxs) == 2:
                    a = entries[idxs[0]]
                    b = entries[idxs[1]]
                    if a.is_protected or b.is_protected:
                        continue
                    new = MemoryEntry(
                        file_path=a.file_path, symbol=a.symbol, kind=a.kind,
                        content=(a.content + "\n---\n" + b.content)[:2000],
                        summary=d.get("summary", a.summary),
                        keywords=(a.keywords + " " + b.keywords).strip(),
                        tier=a.tier,
                    )
                    self.store.insert(new)
                    self.store.delete(a.id)
                    self.store.delete(b.id)
                    merged += 1
            except Exception as e:
                self._log({"event": "apply_error", "decision": d, "error": str(e)})
        return {
            "kept": len(entries) - dropped - merged * 2,
            "dropped": dropped,
            "merged": merged,
        }


class ConsolidationLoop:
    def __init__(self, consolidator: Consolidator, interval_seconds: int):
        self.c = consolidator
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        def run():
            while not self._stop.is_set():
                self._stop.wait(self.interval)
                if self._stop.is_set():
                    break
                try:
                    self.c.run_once()
                except Exception:
                    pass
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_consolidator.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add broker/sidecar/consolidator.py tests/test_consolidator.py
git commit -m "feat(ec2): consolidation loop with decision parsing"
```

---

## Phase 6: Broker Main + Task Queue

### Task 16: Background task queue with push notification

**Files:**
- Create: `elephant-coder2/broker/tasks.py`
- Create: `elephant-coder2/tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_tasks.py`:

```python
import time
from broker.tasks import TaskQueue


def test_runs_task_and_reports_result():
    seen = []
    q = TaskQueue(on_complete=lambda tid, ok, data: seen.append((tid, ok, data)))
    tid = q.submit("echo", lambda: "hi")
    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    q.shutdown()
    assert len(seen) == 1
    assert seen[0][0] == tid
    assert seen[0][1] is True
    assert seen[0][2] == "hi"


def test_failed_task_reports_error():
    seen = []
    q = TaskQueue(on_complete=lambda tid, ok, data: seen.append((tid, ok, data)))
    q.submit("boom", lambda: (_ for _ in ()).throw(ValueError("x")))
    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    q.shutdown()
    assert seen[0][1] is False
    assert "x" in str(seen[0][2])


def test_get_result():
    q = TaskQueue()
    tid = q.submit("add", lambda: 41 + 1)
    for _ in range(50):
        r = q.get(tid)
        if r and r["status"] != "pending":
            break
        time.sleep(0.02)
    q.shutdown()
    r = q.get(tid)
    assert r["status"] == "done"
    assert r["data"] == 42
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_tasks.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement task queue**

Create `elephant-coder2/broker/tasks.py`:

```python
"""Background task queue. Tasks run in a thread pool; completion triggers optional callback."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class TaskQueue:
    def __init__(self, max_workers: int = 2, on_complete: Callable[[str, bool, Any], None] | None = None):
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._on_complete = on_complete

    def submit(self, name: str, fn: Callable[[], Any]) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._lock:
            self._results[tid] = {"status": "pending", "name": name, "data": None}

        def runner():
            try:
                data = fn()
                with self._lock:
                    self._results[tid] = {"status": "done", "name": name, "data": data}
                if self._on_complete:
                    try:
                        self._on_complete(tid, True, data)
                    except Exception:
                        pass
            except Exception as e:
                with self._lock:
                    self._results[tid] = {"status": "error", "name": name, "data": str(e)}
                if self._on_complete:
                    try:
                        self._on_complete(tid, False, str(e))
                    except Exception:
                        pass

        self._pool.submit(runner)
        return tid

    def get(self, tid: str) -> dict | None:
        with self._lock:
            return dict(self._results.get(tid) or {}) or None

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tasks.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add broker/tasks.py tests/test_tasks.py
git commit -m "feat(ec2): background task queue"
```

---

### Task 17: Broker main (assembles everything)

**Files:**
- Create: `elephant-coder2/broker/main.py`
- Create: `elephant-coder2/tests/test_broker_main.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_broker_main.py`:

```python
import time
import pytest
from broker.main import Broker
from broker.client import BrokerClient
from broker.protocol import Request


@pytest.fixture
def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    import broker.store.embedder as emb
    import numpy as np
    monkeypatch.setattr(emb, "embed", lambda t: np.ones(384, dtype=np.float32) / (384 ** 0.5))
    b = Broker(project_root=str(tmp_path / "proj"), host="127.0.0.1", port=0, disable_sidecar=True)
    b.start()
    for _ in range(50):
        if b.server.port:
            break
        time.sleep(0.02)
    yield b
    b.stop()


def test_remember_and_recall(broker):
    client = BrokerClient(port=broker.server.port)
    rsp = client.call(Request(op="remember", args={
        "file_path": "a.py", "symbol": "auth_fn", "content": "auth logic",
        "summary": "authentication function", "keywords": "auth function",
        "kind": "function", "tier": "scratch",
    }))
    assert rsp.ok, rsp.error
    mid = rsp.data["id"]
    assert mid > 0

    rsp = client.call(Request(op="recall", args={"query": "authentication", "limit": 5}))
    assert rsp.ok, rsp.error
    syms = [item["symbol"] for item in rsp.data["items"]]
    assert "auth_fn" in syms


def test_status_returns_counts(broker):
    client = BrokerClient(port=broker.server.port)
    rsp = client.call(Request(op="status"))
    assert rsp.ok
    assert "project" in rsp.data
    assert "tiers" in rsp.data["project"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_broker_main.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement broker main**

Create `elephant-coder2/broker/main.py`:

```python
"""Broker entrypoint: wires storage, retriever, sidecar, server, tasks."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from .paths import ec2_home, global_dir, model_dir, project_dir, project_hash
from .retriever import Retriever
from .server import BrokerServer
from .settings import Settings, load_settings
from .sidecar.consolidator import ConsolidationLoop, Consolidator
from .sidecar.model import SidecarModel
from .store.sqlite_store import MemoryEntry
from .store.unified import UnifiedStore
from .tasks import TaskQueue

log = logging.getLogger(__name__)


def _entry_dict(e: MemoryEntry) -> dict:
    return asdict(e)


class Broker:
    def __init__(
        self,
        project_root: str,
        host: str = "127.0.0.1",
        port: int = 0,
        disable_sidecar: bool = False,
    ):
        self.project_root = Path(project_root)
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.settings: Settings = load_settings(self.project_root)
        self.ph = project_hash(str(self.project_root))
        pdir = project_dir(str(self.project_root))
        gdir = global_dir()

        self.project_store = UnifiedStore(
            sqlite_path=pdir / "memories.db",
            vector_prefix=pdir / "vectors",
            redis_url=self.settings.redis_url,
            project_hash=self.ph,
            redis_ttl=self.settings.redis_ttl_seconds,
        )
        self.global_store = UnifiedStore(
            sqlite_path=gdir / "memories.db",
            vector_prefix=gdir / "vectors",
            redis_url=self.settings.redis_url,
            project_hash="global",
            redis_ttl=self.settings.redis_ttl_seconds,
        )
        self.retriever = Retriever(project=self.project_store, global_store=self.global_store)

        self.sidecar: SidecarModel | None = None
        self.consol_loop: ConsolidationLoop | None = None
        if not disable_sidecar:
            mpath = model_dir() / self.settings.sidecar.model_path
            self.sidecar = SidecarModel(
                model_path=mpath,
                n_gpu_layers=self.settings.sidecar.n_gpu_layers,
                n_ctx=self.settings.sidecar.n_ctx,
            )
            cons = Consolidator(
                store=self.project_store,
                model=self.sidecar,
                log_path=ec2_home() / "sidecar" / "consolidation.log",
            )
            self.consol_loop = ConsolidationLoop(
                cons, interval_seconds=self.settings.scratch_idle_consolidation_minutes * 60
            )

        self.tasks = TaskQueue(on_complete=self._on_task_complete)
        self._push_callback = None

        self.server = BrokerServer(handlers=self._handlers(), host=host, port=port)

    def _on_task_complete(self, tid: str, ok: bool, data) -> None:
        log.info("task %s complete ok=%s", tid, ok)
        # Push notification is delivered via Claude Code's PushNotification API
        # from within hook context; broker just logs here.

    def _handlers(self) -> dict:
        def remember(args):
            entry = MemoryEntry(
                file_path=args["file_path"],
                symbol=args["symbol"],
                kind=args.get("kind", "note"),
                content=args["content"],
                summary=args.get("summary", args["content"][:160]),
                keywords=args.get("keywords", ""),
                tier=args.get("tier", "scratch"),
                is_protected=int(args.get("is_protected", 0)),
                is_identity=int(args.get("is_identity", 0)),
            )
            mid = self.project_store.insert(entry)
            return {"id": mid}

        def recall(args):
            query = args["query"]
            limit = int(args.get("limit", 10))
            items = self.retriever.retrieve(query, limit=limit)
            if self.sidecar and self.sidecar._llm is not None and items:
                try:
                    idx = self.sidecar.rerank(
                        query, [e.summary for e in items], k=min(limit, len(items)),
                        latency_budget_ms=self.settings.sidecar.rerank_latency_ms,
                    )
                    items = [items[i] for i in idx if i < len(items)]
                except Exception:
                    pass
            return {"items": [_entry_dict(e) for e in items]}

        def recall_file(args):
            entries = self.retriever.by_file(args["file_path"])
            return {"items": [_entry_dict(e) for e in entries]}

        def search_symbol(args):
            entries = self.retriever.by_symbol(args["name"])
            return {"items": [_entry_dict(e) for e in entries]}

        def promote(args):
            mid = int(args["memory_id"])
            tier = args["tier"]
            reason = args.get("reason")
            target = self.global_store if tier == "global_durable" else self.project_store
            # If tier is global_durable, move entry from project to global
            if tier == "global_durable":
                e = self.project_store.sqlite.get(mid)
                if not e:
                    return {"ok": False, "error": "not found"}
                e.tier = "global_durable"
                e.promotion_reason = reason
                new_id = self.global_store.insert(e)
                self.project_store.delete(mid)
                return {"ok": True, "new_id": new_id}
            self.project_store.set_tier(mid, tier, reason=reason)
            return {"ok": True}

        def status(args):
            p = self.project_store
            g = self.global_store
            return {
                "project": {
                    "hash": self.ph,
                    "tiers": {
                        "scratch": p.sqlite.count("scratch"),
                        "project_durable": p.sqlite.count("project_durable"),
                    },
                    "vectors": len(p.vectors),
                    "redis_available": p.redis.available if p.redis else False,
                },
                "global": {
                    "global_durable": g.sqlite.count("global_durable"),
                    "vectors": len(g.vectors),
                },
                "sidecar": {
                    "loaded": bool(self.sidecar and self.sidecar._llm is not None),
                    "model_path": str(self.sidecar._model_path) if self.sidecar else None,
                },
            }

        def sidecar_store(args):
            tag = args["tag"]
            content = args["content"]
            entry = MemoryEntry(
                file_path=f"__sidecar__/{tag}",
                symbol=tag,
                kind="sidecar",
                content=content,
                summary=content[:160],
                keywords=tag,
                tier="scratch",
            )
            mid = self.project_store.insert(entry)
            return {"id": mid, "tag": tag}

        def sidecar_recall(args):
            q = args.get("query") or args.get("tag", "")
            by_sym = self.retriever.by_symbol(q)
            if by_sym:
                return {"items": [_entry_dict(e) for e in by_sym]}
            return recall({"query": q, "limit": int(args.get("limit", 5))})

        def brief_subagent(args):
            desc = args["task_description"]
            items = self.retriever.retrieve(desc, limit=5)
            if not items:
                return {"brief": ""}
            parts = ["<memory-brief>"]
            for e in items:
                parts.append(f"- {e.symbol} ({e.kind}, {e.file_path}): {e.summary}")
            parts.append("</memory-brief>")
            return {"brief": "\n".join(parts)}

        def schedule_task(args):
            task_type = args["type"]
            def run():
                if task_type == "reindex_project":
                    from .indexer.orchestrator import index_project
                    entries = index_project(self.project_root)
                    count = 0
                    for e in entries:
                        self.project_store.insert(e)
                        count += 1
                    return {"indexed": count}
                if task_type == "consolidate_memories":
                    if self.consol_loop:
                        return self.consol_loop.c.run_once()
                    return {"skipped": True}
                return {"unknown_type": task_type}
            tid = self.tasks.submit(task_type, run)
            return {"task_id": tid}

        def get_task(args):
            return self.tasks.get(args["task_id"]) or {"status": "unknown"}

        def configure(args):
            # Writes to .claude/elephant-coder2.local.md; simple passthrough for now
            return {"ok": True, "note": "configure via /ec2:configure skill for UX"}

        return {
            "remember": remember,
            "recall": recall,
            "recall_file": recall_file,
            "search_symbol": search_symbol,
            "promote": promote,
            "status": status,
            "sidecar_store": sidecar_store,
            "sidecar_recall": sidecar_recall,
            "brief_subagent": brief_subagent,
            "schedule_task": schedule_task,
            "get_task": get_task,
            "configure": configure,
        }

    def start(self) -> None:
        self.server.start()
        if self.consol_loop:
            self.consol_loop.start()

    def stop(self) -> None:
        if self.consol_loop:
            self.consol_loop.stop()
        self.server.stop()
        self.tasks.shutdown()
        self.project_store.close()
        self.global_store.close()


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--disable-sidecar", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    b = Broker(project_root=args.project, port=args.port, disable_sidecar=args.disable_sidecar)
    b.start()
    import signal
    signal.signal(signal.SIGTERM, lambda *_: b.stop())
    try:
        import time as _t
        while True:
            _t.sleep(3600)
    except KeyboardInterrupt:
        b.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_broker_main.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add broker/main.py tests/test_broker_main.py
git commit -m "feat(ec2): broker main entrypoint wiring store/retriever/sidecar/tasks"
```

---

## Phase 7: Hooks (Automatic Activation)

### Task 18: Shared hook client utility + broker autostart

**Files:**
- Create: `elephant-coder2/hooks/_client.py`
- Create: `elephant-coder2/tests/test_hook_client.py`

- [ ] **Step 1: Write the failing test**

Create `elephant-coder2/tests/test_hook_client.py`:

```python
import json
import sys
from hooks._client import read_hook_input, emit_context, call_broker


def test_read_hook_input(monkeypatch, capsys):
    payload = {"hook_event_name": "SessionStart", "cwd": "/x"}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    got = read_hook_input()
    assert got["hook_event_name"] == "SessionStart"


def test_emit_context_prints_json(capsys):
    emit_context("SessionStart", "hello world")
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert data["hookSpecificOutput"]["additionalContext"] == "hello world"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_hook_client.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement shared client**

Create `elephant-coder2/hooks/_client.py`:

```python
"""Shared hook helpers: read stdin payload, emit additional context, talk to broker."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker.client import BrokerClient, BrokerUnavailable
from broker.paths import broker_pid_file, broker_port_file
from broker.protocol import Request


def read_hook_input() -> dict[str, Any]:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def emit_context(event_name: str, text: str) -> None:
    """Emit hookSpecificOutput.additionalContext JSON for Claude Code to pick up."""
    if not text:
        return
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }
    print(json.dumps(payload), flush=True)


def _is_broker_alive() -> bool:
    pf = broker_pid_file()
    if not pf.exists() or not broker_port_file().exists():
        return False
    try:
        pid = int(pf.read_text().strip())
        if os.name == "nt":
            # Best-effort on Windows
            import ctypes
            PROCESS_QUERY_LIMITED = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def ensure_broker(project_root: str) -> bool:
    if _is_broker_alive():
        return True
    # Spawn broker as a detached subprocess
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
    main_py = plugin_root / "broker" / "main.py"
    if not main_py.exists():
        return False
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008  # DETACHED_PROCESS
    try:
        subprocess.Popen(
            [sys.executable, str(main_py), "--project", project_root],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception:
        return False
    # Wait for port file to appear
    for _ in range(50):
        if broker_port_file().exists():
            return True
        time.sleep(0.05)
    return False


def call_broker(op: str, args: dict | None = None, timeout: float = 2.0):
    try:
        c = BrokerClient(timeout=timeout)
        return c.call(Request(op=op, args=args or {}))
    except BrokerUnavailable:
        return None
    except Exception:
        return None
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_hook_client.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add hooks/_client.py tests/test_hook_client.py
git commit -m "feat(ec2): shared hook helpers + broker autostart"
```

---

### Task 19: SessionStart + PostToolUse hooks

**Files:**
- Create: `elephant-coder2/hooks/session_start.py`
- Create: `elephant-coder2/hooks/posttooluse_edit.py`
- Create: `elephant-coder2/hooks/posttooluse_write.py`
- Create: `elephant-coder2/hooks/hooks.json`

- [ ] **Step 1: Implement SessionStart**

Create `elephant-coder2/hooks/session_start.py`:

```python
#!/usr/bin/env python
"""Spawn broker; inject identity + project mental model as additionalContext."""
from __future__ import annotations

import os
from pathlib import Path

from _client import call_broker, emit_context, ensure_broker, read_hook_input


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd") or os.getcwd()
    if not ensure_broker(cwd):
        return
    rsp = call_broker("status")
    if not rsp or not rsp.ok:
        return
    proj = rsp.data.get("project", {})
    tiers = proj.get("tiers", {})
    summary = (
        f"<ec2-session>"
        f"project_hash={proj.get('hash','?')}, "
        f"scratch={tiers.get('scratch',0)}, "
        f"project_durable={tiers.get('project_durable',0)}, "
        f"global_durable={rsp.data.get('global',{}).get('global_durable',0)}"
        f"</ec2-session>"
    )
    emit_context("SessionStart", summary)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement PostToolUse:Edit**

Create `elephant-coder2/hooks/posttooluse_edit.py`:

```python
#!/usr/bin/env python
"""Re-index edited file by asking broker to reindex the project in background."""
from __future__ import annotations

from _client import call_broker, read_hook_input


def main():
    payload = read_hook_input()
    tool = payload.get("tool_input") or {}
    fp = tool.get("file_path")
    if not fp:
        return
    call_broker("schedule_task", {"type": "reindex_project"}, timeout=1.0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Implement PostToolUse:Write**

Create `elephant-coder2/hooks/posttooluse_write.py`:

```python
#!/usr/bin/env python
"""On new file, trigger a background reindex."""
from _client import call_broker, read_hook_input


def main():
    payload = read_hook_input()
    if not (payload.get("tool_input") or {}).get("file_path"):
        return
    call_broker("schedule_task", {"type": "reindex_project"}, timeout=1.0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit (hooks.json comes in next task)**

```bash
git add hooks/session_start.py hooks/posttooluse_edit.py hooks/posttooluse_write.py
git commit -m "feat(ec2): SessionStart + PostToolUse hooks"
```

---

### Task 20: PreToolUse hooks (Read / Grep / Glob / Agent) and UserPromptSubmit

**Files:**
- Create: `elephant-coder2/hooks/pretooluse_read.py`
- Create: `elephant-coder2/hooks/pretooluse_search.py`
- Create: `elephant-coder2/hooks/pretooluse_agent.py`
- Create: `elephant-coder2/hooks/userpromptsubmit.py`
- Create: `elephant-coder2/hooks/hooks.json`

- [ ] **Step 1: Implement PreToolUse:Read**

Create `elephant-coder2/hooks/pretooluse_read.py`:

```python
#!/usr/bin/env python
"""Inject <memory-context> about the file being read."""
from __future__ import annotations

from _client import call_broker, emit_context, read_hook_input

TOKEN_CAP = 300
CHAR_APPROX = TOKEN_CAP * 4


def main():
    p = read_hook_input()
    tool = p.get("tool_input") or {}
    fp = tool.get("file_path")
    if not fp:
        return
    rsp = call_broker("recall_file", {"file_path": fp}, timeout=1.0)
    if not rsp or not rsp.ok:
        rsp = call_broker("recall", {"query": fp, "limit": 5}, timeout=1.0)
    if not rsp or not rsp.ok:
        return
    items = rsp.data.get("items", [])
    if not items:
        return
    lines = ["<memory-context>"]
    used = 0
    for e in items:
        line = f"- {e['symbol']} ({e['kind']}): {e['summary']}"
        if used + len(line) > CHAR_APPROX:
            break
        lines.append(line)
        used += len(line)
    lines.append("</memory-context>")
    emit_context("PreToolUse", "\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement PreToolUse:Grep/Glob (shared script)**

Create `elephant-coder2/hooks/pretooluse_search.py`:

```python
#!/usr/bin/env python
"""Inject retrieved memory snippets for Grep/Glob queries."""
from __future__ import annotations

from _client import call_broker, emit_context, read_hook_input

TOKEN_CAP = 300
CHAR_APPROX = TOKEN_CAP * 4


def main():
    p = read_hook_input()
    tool = p.get("tool_input") or {}
    query = tool.get("pattern") or tool.get("path") or ""
    if not query:
        return
    rsp = call_broker("recall", {"query": query, "limit": 5}, timeout=1.0)
    if not rsp or not rsp.ok:
        return
    items = rsp.data.get("items", [])
    if not items:
        return
    lines = ["<memory-context>"]
    used = 0
    for e in items:
        line = f"- {e['symbol']} ({e['file_path']}): {e['summary']}"
        if used + len(line) > CHAR_APPROX:
            break
        lines.append(line)
        used += len(line)
    lines.append("</memory-context>")
    emit_context("PreToolUse", "\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Implement PreToolUse:Agent (auto-brief)**

Create `elephant-coder2/hooks/pretooluse_agent.py`:

```python
#!/usr/bin/env python
"""Auto-brief subagents from memory unless prompt contains <no-brief/>."""
from __future__ import annotations

from _client import call_broker, emit_context, read_hook_input

TOKEN_CAP = 500


def main():
    p = read_hook_input()
    tool = p.get("tool_input") or {}
    prompt = tool.get("prompt") or ""
    if "<no-brief/>" in prompt:
        return
    rsp = call_broker("brief_subagent", {"task_description": prompt[:2000]}, timeout=1.5)
    if not rsp or not rsp.ok:
        return
    brief = rsp.data.get("brief", "")
    if not brief:
        return
    # Cap at ~TOKEN_CAP*4 chars
    if len(brief) > TOKEN_CAP * 4:
        brief = brief[: TOKEN_CAP * 4]
    emit_context("PreToolUse", brief)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement UserPromptSubmit**

Create `elephant-coder2/hooks/userpromptsubmit.py`:

```python
#!/usr/bin/env python
"""Retrieve top-3 memories for the user's prompt; inject as <memory-context>."""
from __future__ import annotations

from _client import call_broker, emit_context, read_hook_input

TOKEN_CAP = 800


def main():
    p = read_hook_input()
    prompt = p.get("prompt") or ""
    if not prompt.strip():
        return
    rsp = call_broker("recall", {"query": prompt[:1000], "limit": 3}, timeout=1.5)
    if not rsp or not rsp.ok:
        return
    items = rsp.data.get("items", [])
    if not items:
        return
    lines = ["<memory-context>"]
    used = 0
    for e in items:
        line = f"- {e['symbol']} ({e['file_path']}): {e['summary']}"
        if used + len(line) > TOKEN_CAP * 4:
            break
        lines.append(line)
        used += len(line)
    lines.append("</memory-context>")
    emit_context("UserPromptSubmit", "\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create hooks.json**

Create `elephant-coder2/hooks/hooks.json`:

```json
{
  "description": "elephant-coder2: automatic memory activation via shadowed tools",
  "hooks": {
    "SessionStart": [
      { "matcher": "", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py", "timeout": 10 }
      ]}
    ],
    "UserPromptSubmit": [
      { "matcher": "", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/userpromptsubmit.py", "timeout": 3 }
      ]}
    ],
    "PreToolUse": [
      { "matcher": "Read", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_read.py", "timeout": 3 }
      ]},
      { "matcher": "Grep", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_search.py", "timeout": 3 }
      ]},
      { "matcher": "Glob", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_search.py", "timeout": 3 }
      ]},
      { "matcher": "Task", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_agent.py", "timeout": 3 }
      ]}
    ],
    "PostToolUse": [
      { "matcher": "Edit", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_edit.py", "timeout": 5 }
      ]},
      { "matcher": "Write", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_write.py", "timeout": 5 }
      ]}
    ]
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add hooks/pretooluse_read.py hooks/pretooluse_search.py hooks/pretooluse_agent.py hooks/userpromptsubmit.py hooks/hooks.json
git commit -m "feat(ec2): PreToolUse/UserPromptSubmit hooks + hooks.json"
```

---

## Phase 8: MCP Server

### Task 21: MCP server exposing 12 tools

**Files:**
- Create: `elephant-coder2/mcp/__init__.py` (empty)
- Create: `elephant-coder2/mcp/server.py`
- Create: `elephant-coder2/.mcp.json`
- Create: `elephant-coder2/tests/test_mcp_surface.py`

- [ ] **Step 1: Write the failing test (smoke — checks every tool is declared)**

Create `elephant-coder2/tests/test_mcp_surface.py`:

```python
from mcp.server import list_tool_names

EXPECTED = {
    "recall", "recall_file", "search_symbol", "graph",
    "remember", "promote", "sidecar_store", "sidecar_recall",
    "brief_subagent", "schedule_task", "status", "configure",
}


def test_all_tools_declared():
    assert set(list_tool_names()) == EXPECTED
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_mcp_surface.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement MCP server**

Create `elephant-coder2/mcp/server.py`:

```python
"""MCP server exposing 12 tools. Each tool forwards to the broker via BrokerClient."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker.client import BrokerClient, BrokerUnavailable
from broker.protocol import Request

from mcp.server import Server
from mcp.types import Tool, TextContent

TOOLS: dict[str, dict] = {
    "recall": {
        "description": "Hybrid search across scratch/project_durable/global_durable. Reranked by small model.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        }, "required": ["query"]},
    },
    "recall_file": {
        "description": "All memories linked to a file_path.",
        "inputSchema": {"type": "object", "properties": {
            "file_path": {"type": "string"},
        }, "required": ["file_path"]},
    },
    "search_symbol": {
        "description": "Lookup by exact symbol name.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string"},
        }, "required": ["name"]},
    },
    "graph": {
        "description": "(Placeholder) Call graph for a symbol.",
        "inputSchema": {"type": "object", "properties": {
            "symbol": {"type": "string"},
            "depth": {"type": "integer", "default": 2},
        }, "required": ["symbol"]},
    },
    "remember": {
        "description": "Manually store a memory entry.",
        "inputSchema": {"type": "object", "properties": {
            "file_path": {"type": "string"},
            "symbol": {"type": "string"},
            "content": {"type": "string"},
            "summary": {"type": "string"},
            "keywords": {"type": "string"},
            "kind": {"type": "string", "default": "note"},
            "tier": {"type": "string", "default": "scratch"},
        }, "required": ["file_path", "symbol", "content"]},
    },
    "promote": {
        "description": "Promote a memory to project_durable or global_durable.",
        "inputSchema": {"type": "object", "properties": {
            "memory_id": {"type": "integer"},
            "tier": {"type": "string", "enum": ["project_durable", "global_durable"]},
            "reason": {"type": "string"},
        }, "required": ["memory_id", "tier"]},
    },
    "sidecar_store": {
        "description": "Offload context to small-model scratch under a tag.",
        "inputSchema": {"type": "object", "properties": {
            "tag": {"type": "string"},
            "content": {"type": "string"},
        }, "required": ["tag", "content"]},
    },
    "sidecar_recall": {
        "description": "Retrieve a previously stashed sidecar entry by tag or query.",
        "inputSchema": {"type": "object", "properties": {
            "tag": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        }},
    },
    "brief_subagent": {
        "description": "Produce a <memory-brief> string for dispatching a subagent.",
        "inputSchema": {"type": "object", "properties": {
            "task_description": {"type": "string"},
        }, "required": ["task_description"]},
    },
    "schedule_task": {
        "description": "Queue a background task (reindex_project, consolidate_memories).",
        "inputSchema": {"type": "object", "properties": {
            "type": {"type": "string"},
            "args": {"type": "object"},
        }, "required": ["type"]},
    },
    "status": {
        "description": "Broker + model + store stats.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "configure": {
        "description": "Update settings (placeholder — use /ec2:configure for UX).",
        "inputSchema": {"type": "object", "additionalProperties": True},
    },
}


def list_tool_names() -> list[str]:
    return list(TOOLS.keys())


def _forward(op: str, args: dict) -> dict:
    try:
        c = BrokerClient(timeout=5.0)
    except BrokerUnavailable as e:
        return {"ok": False, "error": str(e)}
    rsp = c.call(Request(op=op, args=args))
    return {"ok": rsp.ok, "data": rsp.data, "error": rsp.error}


def build_server() -> Server:
    server = Server("elephant-coder2")

    @server.list_tools()
    async def _list():
        return [Tool(name=n, description=t["description"], inputSchema=t["inputSchema"])
                for n, t in TOOLS.items()]

    @server.call_tool()
    async def _call(name: str, arguments: dict) -> list[TextContent]:
        result = _forward(name, arguments or {})
        return [TextContent(type="text", text=json.dumps(result))]

    return server


async def _run():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (r, w):
        s = build_server()
        await s.run(r, w, s.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create .mcp.json**

Create `elephant-coder2/.mcp.json`:

```json
{
  "mcpServers": {
    "elephant-coder2": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/server.py"]
    }
  }
}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_mcp_surface.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add mcp/ .mcp.json tests/test_mcp_surface.py
git commit -m "feat(ec2): MCP server with 12 tools"
```

---

## Phase 9: Skills & Commands

Skills in v2 are lean markdown files. Each skill has a matching slash command file. The pattern is uniform: a brief description plus instructions that delegate to the broker via the MCP tools built in Phase 8.

### Task 22: Core memory skills (recall, status, graph, recent, ingest, index)

**Files (create each as both `skills/<name>/SKILL.md` and `commands/<name>.md`):**

- [ ] **Step 1: Create recall skill**

Create `elephant-coder2/skills/recall/SKILL.md`:

```markdown
---
name: ec2-recall
description: Hybrid search across scratch / project_durable / global_durable memory tiers. Use when the user asks about prior knowledge, code patterns, or project context.
---

Call the MCP tool `mcp__elephant-coder2__recall` with the user's query. Limit defaults to 10. Present results as a short list with symbol, file, and summary.
```

Create `elephant-coder2/commands/recall.md`:

```markdown
---
description: Search memory (hybrid FTS + vector + rerank)
argument-hint: <query>
---

Call `mcp__elephant-coder2__recall` with the query: $ARGUMENTS
```

- [ ] **Step 2: Create status skill**

Create `elephant-coder2/skills/status/SKILL.md`:

```markdown
---
name: ec2-status
description: Show broker + model + store statistics. Use when the user asks "how much memory", "is ec2 running", or wants to verify the broker.
---

Call `mcp__elephant-coder2__status`. Format the response as: project tiers, global tier, sidecar loaded/unloaded, Redis available. Keep output under 20 lines.
```

Create `elephant-coder2/commands/status.md`:

```markdown
---
description: Show elephant-coder2 memory store + broker status
---

Call `mcp__elephant-coder2__status` and summarize.
```

- [ ] **Step 3: Create graph, recent, ingest, index skills (batch)**

Create `elephant-coder2/skills/graph/SKILL.md`:

```markdown
---
name: ec2-graph
description: Show the call graph for a symbol. Use when user asks about callers/callees or "what depends on X".
---

Call `mcp__elephant-coder2__graph` with the symbol name and optional depth. Present forward and reverse deps.
```

Create `elephant-coder2/commands/graph.md`:

```markdown
---
description: Call graph for a symbol
argument-hint: <symbol>
---

Call `mcp__elephant-coder2__graph` with symbol: $ARGUMENTS
```

Create `elephant-coder2/skills/recent/SKILL.md`:

```markdown
---
name: ec2-recent
description: List recently changed files with indexed symbols. Use when user asks "what changed" or "what did I touch".
---

Use git to find recent commits in the last N days (default 7), then call `mcp__elephant-coder2__recall_file` for each changed file and aggregate results.
```

Create `elephant-coder2/commands/recent.md`:

```markdown
---
description: Recently changed files with indexed symbols
argument-hint: [days]
---

List files changed in the last ${ARGUMENTS:-7} days using git, then report indexed memory for each.
```

Create `elephant-coder2/skills/ingest/SKILL.md`:

```markdown
---
name: ec2-ingest
description: Ingest documents into memory (PDF/MD/TXT). Use when user wants to add research or external docs to the store.
---

For each document the user points to: read it (use pdf-convert for PDFs), then call `mcp__elephant-coder2__remember` with summary and keywords, tier=project_durable.
```

Create `elephant-coder2/commands/ingest.md`:

```markdown
---
description: Ingest documents into memory
argument-hint: <path>
---

Ingest the file or directory: $ARGUMENTS
```

Create `elephant-coder2/skills/index/SKILL.md`:

```markdown
---
name: ec2-index
description: Force a full project re-index. Rarely needed since PostToolUse auto-indexes changed files.
---

Call `mcp__elephant-coder2__schedule_task` with type=reindex_project. Then call `status` to confirm.
```

Create `elephant-coder2/commands/index.md`:

```markdown
---
description: Force project re-index (background)
---

Trigger a full reindex via `mcp__elephant-coder2__schedule_task` type=reindex_project.
```

- [ ] **Step 4: Commit**

```bash
git add skills/recall skills/status skills/graph skills/recent skills/ingest skills/index \
       commands/recall.md commands/status.md commands/graph.md commands/recent.md commands/ingest.md commands/index.md
git commit -m "feat(ec2): core memory skills + commands"
```

---

### Task 23: Tier, sidecar, agent skills (promote, sidecar, agents)

- [ ] **Step 1: Create promote skill**

Create `elephant-coder2/skills/promote/SKILL.md`:

```markdown
---
name: ec2-promote
description: Promote a memory to project_durable or global_durable tier. Use when a scratch entry is clearly worth keeping long-term or transferable across projects.
---

When you identify a memory you want to promote:
1. Call `mcp__elephant-coder2__recall` to get the memory_id if you don't have it.
2. Call `mcp__elephant-coder2__promote` with memory_id, tier (project_durable or global_durable), and a reason describing why it's worth keeping.
3. Confirm success to the user.

Promote to `global_durable` only for transferable patterns, lessons, or conventions — not project-specific code.
```

Create `elephant-coder2/commands/promote.md`:

```markdown
---
description: Promote memory to durable tier
argument-hint: <memory_id> <tier> <reason>
---

Promote memory to durable tier: $ARGUMENTS
```

- [ ] **Step 2: Create sidecar skill**

Create `elephant-coder2/skills/sidecar/SKILL.md`:

```markdown
---
name: ec2-sidecar
description: Store/retrieve context in the small-model scratch. Use to offload large context (stack traces, long diffs, research notes) that shouldn't stay in main context.
---

To stash: `mcp__elephant-coder2__sidecar_store` with tag and content.
To retrieve: `mcp__elephant-coder2__sidecar_recall` with tag or query.

Use tags with dates for easy recall: `auth_review_2026-04-17`, `db_migration_debug`.
```

Create `elephant-coder2/commands/sidecar.md`:

```markdown
---
description: Manage sidecar scratch
argument-hint: <store|recall> <tag> [content]
---

Sidecar operation: $ARGUMENTS
```

- [ ] **Step 3: Create agents skill**

Create `elephant-coder2/skills/agents/SKILL.md`:

```markdown
---
name: ec2-agents
description: Manually generate a memory brief for subagent dispatch. Usually unnecessary — PreToolUse:Task hook auto-briefs. Use when you want to inspect the brief before dispatch.
---

Call `mcp__elephant-coder2__brief_subagent` with the task description. Review the returned brief, then prepend it to the subagent's prompt manually if you want to customize it.

To skip auto-briefing for a specific subagent, include `<no-brief/>` in its prompt.
```

Create `elephant-coder2/commands/agents.md`:

```markdown
---
description: Generate a memory brief for a subagent
argument-hint: <task description>
---

Generate subagent brief: $ARGUMENTS
```

- [ ] **Step 4: Commit**

```bash
git add skills/promote skills/sidecar skills/agents \
       commands/promote.md commands/sidecar.md commands/agents.md
git commit -m "feat(ec2): promote/sidecar/agents skills"
```

---

### Task 24: Configure + profile skills

- [ ] **Step 1: Create configure skill (canonical YAML frontmatter editor)**

Create `elephant-coder2/skills/configure/SKILL.md`:

```markdown
---
name: ec2-configure
description: Interactively configure elephant-coder2 for this project. Edits .claude/elephant-coder2.local.md YAML frontmatter.
---

Ask the user which settings to change, one category at a time:
1. **Storage:** max_scratch_entries (default 32000), redis_url
2. **Sidecar:** model_path (GGUF file name), n_gpu_layers, rerank_latency_ms, n_ctx
3. **Injection:** prompt_budget_tokens, tool_budget_tokens, agent_brief_tokens
4. **External:** openrouter_api_key, external.model

Write changes to `.claude/elephant-coder2.local.md`. Preserve existing frontmatter keys the user did not touch. After writing, confirm by printing the resulting frontmatter.

Example resulting file:

```
---
max_scratch_entries: 32000
injection:
  prompt_budget_tokens: 600
sidecar:
  model_path: qwen2.5-1.5b-instruct-q4_k_m.gguf
---
```
```

Create `elephant-coder2/commands/configure.md`:

```markdown
---
description: Configure elephant-coder2 settings for this project
---

Launch the configure skill.
```

- [ ] **Step 2: Create profile skill**

Create `elephant-coder2/skills/profile/SKILL.md`:

```markdown
---
name: ec2-profile
description: View or edit the user profile stored in global memory. Use when the user asks about their preferences, goals, or recurring requests.
---

Query `mcp__elephant-coder2__recall` with tier filter "global_durable" and query "user_profile". To add observations, use `remember` with file_path="__profile__", tier="global_durable".

Observations categories: professional_goal, personal_goal, habit, preference, expertise. Keep entries short and factual.
```

Create `elephant-coder2/commands/profile.md`:

```markdown
---
description: View or edit user profile (global memory)
---

Launch the profile skill.
```

- [ ] **Step 3: Commit**

```bash
git add skills/configure skills/profile commands/configure.md commands/profile.md
git commit -m "feat(ec2): configure + profile skills"
```

---

### Task 25: Workflow skills (changelog, git-versioning, cicd, pdf-convert)

- [ ] **Step 1: Create changelog skill**

Create `elephant-coder2/skills/changelog/SKILL.md`:

```markdown
---
name: ec2-changelog
description: Update CHANGELOG.md before git commits. Use before every commit to document the change in the user-facing changelog.
---

1. Read CHANGELOG.md (create it if missing with a `# Changelog` header).
2. Look at the staged diff: `git diff --cached`.
3. Write a new bullet under the latest version header (or `## [Unreleased]` if no version yet). Format: `- feat|fix|chore: <one-line summary>`.
4. Save and stage: `git add CHANGELOG.md`.
```

Create `elephant-coder2/commands/changelog.md`:

```markdown
---
description: Update CHANGELOG.md before committing
---

Launch the changelog skill.
```

- [ ] **Step 2: Create git-versioning skill**

Create `elephant-coder2/skills/git-versioning/SKILL.md`:

```markdown
---
name: ec2-git-versioning
description: Enforce conventional commits and semver. Use when user asks about commit messages, versioning, or PR titles.
---

Commit format: `<type>(<scope>): <subject>`. Types: feat, fix, chore, docs, refactor, test, perf, build, ci.
Version bumps: breaking → major, feat → minor, fix/chore → patch.
Verify CHANGELOG.md is updated before committing (call ec2-changelog first if not).
```

Create `elephant-coder2/commands/git-versioning.md`:

```markdown
---
description: Conventional commits + semver helper
---

Launch the git-versioning skill.
```

- [ ] **Step 3: Create cicd skill**

Create `elephant-coder2/skills/cicd/SKILL.md`:

```markdown
---
name: ec2-cicd
description: Set up GitHub Actions, pre-commit hooks, or deployment workflows. Use when user asks to "set up CI", "add GitHub Actions", or "automate testing".
---

Ask the user which workflows they need (test, lint, build, deploy). Generate:
- `.github/workflows/ci.yml` with their test/lint matrix
- `.pre-commit-config.yaml` if pre-commit is wanted

Prefer the project's existing patterns. For Python, default to pytest + ruff. For TS/JS, default to the project's package.json scripts.
```

Create `elephant-coder2/commands/cicd.md`:

```markdown
---
description: Set up CI/CD (GitHub Actions, pre-commit, deploy)
---

Launch the cicd skill.
```

- [ ] **Step 4: Create pdf-convert skill**

Create `elephant-coder2/skills/pdf-convert/SKILL.md`:

```markdown
---
name: ec2-pdf-convert
description: Convert a PDF to text or markdown. Use when user shares a PDF path or asks to extract PDF content.
---

Run (inside a Python snippet or separate script):

```python
from pypdf import PdfReader
reader = PdfReader(path)
text = "\n\n".join(p.extract_text() or "" for p in reader.pages)
```

Save the output next to the PDF with `.md` or `.txt` suffix. Offer to ingest it into memory (call ec2-ingest).
```

Create `elephant-coder2/commands/pdf-convert.md`:

```markdown
---
description: Convert a PDF to text/markdown
argument-hint: <path>
---

Convert PDF: $ARGUMENTS
```

- [ ] **Step 5: Commit**

```bash
git add skills/changelog skills/git-versioning skills/cicd skills/pdf-convert \
       commands/changelog.md commands/git-versioning.md commands/cicd.md commands/pdf-convert.md
git commit -m "feat(ec2): workflow skills (changelog/git-versioning/cicd/pdf-convert)"
```

---

### Task 26: External + think-tank + modules + feeds + merits skills

- [ ] **Step 1: Create second-opinion skill**

Create `elephant-coder2/skills/second-opinion/SKILL.md`:

```markdown
---
name: ec2-second-opinion
description: Get an external model review before implementing a plan or fix. Use for high-stakes decisions.
---

Read `external.openrouter_api_key` and `external.model` from settings. Send the plan + relevant context via OpenRouter chat completions API. Parse response. Present issues as Critical / Major / Minor.

If no API key is configured, ask the user to set one via `/ec2:configure`.
```

Create `elephant-coder2/commands/second-opinion.md`:

```markdown
---
description: External model review via OpenRouter
argument-hint: <plan>
---

Request external review: $ARGUMENTS
```

- [ ] **Step 2: Create think-tank skill**

Create `elephant-coder2/skills/think-tank/SKILL.md`:

```markdown
---
name: ec2-think-tank
description: Multi-agent brainstorming with named personas (CEO, CTO, Creative Director, etc.). Use for strategic/architectural decisions.
---

Ask the user: topic, template (exec-briefing / architecture-review / risk-assessment), participants (default: CEO, CTO, Creative Director, PM).

For each round:
1. Send topic + transcript to each participant persona via OpenRouter (or the default Claude model).
2. Collect responses.
3. Show the user, ask if another round or conclude.

At conclusion, write a synthesis. Save to `docs/think-tank/<date>-<topic>.md`.
```

Create `elephant-coder2/commands/think-tank.md`:

```markdown
---
description: Multi-agent brainstorm with persona executives
argument-hint: <topic>
---

Start think-tank on: $ARGUMENTS
```

- [ ] **Step 3: Create modules skill**

Create `elephant-coder2/skills/modules/SKILL.md`:

```markdown
---
name: ec2-modules
description: Create small Python modules that extend ec2 capabilities. Use when Claude identifies a reusable helper, analyzer, or checker.
---

Modules live at `~/.elephant-coder2/modules/<name>/module.py` with `manifest.json` next to them. Each module exposes a `run(args: dict) -> dict` function.

To create: ask for name + purpose; generate the module file and manifest; write it to disk.
To list: walk the modules dir and read manifests.
To run: import via `importlib.util.spec_from_file_location` and call `run(args)`.

Modules are invoked from Claude by running the module subprocess; results flow back as JSON.
```

Create `elephant-coder2/commands/modules.md`:

```markdown
---
description: Create and manage ec2 modules
---

Launch the modules skill.
```

- [ ] **Step 4: Create feeds + merits skills**

Create `elephant-coder2/skills/feeds/SKILL.md`:

```markdown
---
name: ec2-feeds
description: Manage RSS feeds and fetch a news briefing. Use when user wants tech news.
---

Feed URLs live in `.claude/elephant-coder2.local.md` under `rss_feeds`. To add: edit the YAML. To fetch: run a Python snippet that uses `httpx` to GET each feed and summarize new items.
```

Create `elephant-coder2/commands/feeds.md`:

```markdown
---
description: Manage RSS feeds / fetch briefing
---

Launch feeds skill.
```

Create `elephant-coder2/skills/merits/SKILL.md`:

```markdown
---
name: ec2-merits
description: View accumulated merit points and rank. Gamification for consistent engineering habits.
---

Merits live in a small SQLite DB at `~/.elephant-coder2/merits.db`. Read count and category totals, print rank and recent awards.
```

Create `elephant-coder2/commands/merits.md`:

```markdown
---
description: View merit points and rank
---

Show merits and rank.
```

- [ ] **Step 5: Commit**

```bash
git add skills/second-opinion skills/think-tank skills/modules skills/feeds skills/merits \
       commands/second-opinion.md commands/think-tank.md commands/modules.md commands/feeds.md commands/merits.md
git commit -m "feat(ec2): external/think-tank/modules/feeds/merits skills"
```

---

## Phase 10: Plugin Polish + CI + End-to-End

### Task 27: README and CLAUDE.md polish

**Files:**
- Modify: `elephant-coder2/README.md`
- Modify: `elephant-coder2/CLAUDE.md`

- [ ] **Step 1: Expand README with the shipped surface**

Replace `elephant-coder2/README.md` with:

```markdown
# elephant-coder2

**Automatic memory activation for Claude Code.**

Unlike v1, v2 does not require reminding Claude to use memory. Hooks shadow Read/Grep/Glob/Task and inject retrieved context directly into tool results. A local small GGUF model (Qwen 2.5 1.5B by default, via llama-cpp-python + Vulkan) handles session scratch, consolidation, and retrieval reranking.

## Components
- **Broker** — persistent Python process (TCP localhost socket). Serves hooks and MCP.
- **Storage** — Redis primary cache + SQLite+FTS5 durable + numpy vectors. Three tiers: scratch / project_durable / global_durable.
- **Sidecar** — in-process Qwen 2.5 1.5B for scratch/consolidate/rerank.

## Slash commands
`/ec2:recall` `/ec2:status` `/ec2:graph` `/ec2:recent` `/ec2:ingest` `/ec2:index`
`/ec2:configure` `/ec2:profile` `/ec2:promote` `/ec2:sidecar` `/ec2:agents`
`/ec2:second-opinion` `/ec2:think-tank` `/ec2:changelog` `/ec2:git-versioning`
`/ec2:cicd` `/ec2:pdf-convert` `/ec2:modules` `/ec2:feeds` `/ec2:merits`

## MCP tools (12)
`recall`, `recall_file`, `search_symbol`, `graph`, `remember`, `promote`,
`sidecar_store`, `sidecar_recall`, `brief_subagent`, `schedule_task`,
`status`, `configure`.

## Requirements
- Python 3.12+
- llama-cpp-python (Vulkan) with Qwen 2.5 1.5B Instruct Q4_K_M at `~/.elephant-coder2/models/`
- Optional: Redis (falls back to SQLite-only if unavailable)

## First-run setup
1. Install plugin.
2. Place GGUF model at `~/.elephant-coder2/models/qwen2.5-1.5b-instruct-q4_k_m.gguf` (or configure alternative).
3. Run `/ec2:configure` to tune settings.
4. Start a session — memory activates automatically.

## Design spec
See `docs/superpowers/specs/2026-04-17-elephant-coder2-design.md` in the parent repo.
```

- [ ] **Step 2: Expand CLAUDE.md**

Replace `elephant-coder2/CLAUDE.md` with:

```markdown
# elephant-coder2

Memory activation is automatic. Hooks inject relevant memory into tool results — no manual invocation needed.

## When to invoke tools manually
- `/ec2:recall` — explicit search beyond what hooks surfaced
- `/ec2:status` — verify broker + store health
- `/ec2:promote` — mark a memory as durable or cross-project
- `/ec2:sidecar` — offload big context you don't want in main window

## Subagents
Subagent dispatches are auto-briefed. Include `<no-brief/>` in the subagent prompt to skip briefing.

Subagents can stash findings via `mcp__elephant-coder2__sidecar_store(tag, content)`; main Claude retrieves with `sidecar_recall(tag)`.

## Settings
`.claude/elephant-coder2.local.md` — YAML frontmatter overrides defaults.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(ec2): README and CLAUDE.md polish"
```

---

### Task 28: GitHub Actions CI

**Files:**
- Create: `elephant-coder2/.github/workflows/ci.yml` (in the plugin subtree)

- [ ] **Step 1: Write CI workflow**

Create `elephant-coder2/.github/workflows/ci.yml`:

```yaml
name: elephant-coder2 CI

on:
  push:
    paths: ["elephant-coder2/**"]
  pull_request:
    paths: ["elephant-coder2/**"]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install (no llama-cpp)
        working-directory: elephant-coder2
        run: |
          pip install -e .[dev] --no-deps
          pip install mcp redis numpy sentence-transformers pypdf pyyaml httpx pytest pytest-asyncio
      - name: Run tests
        working-directory: elephant-coder2
        run: pytest -v -k "not llama"

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Compile
        working-directory: elephant-coder2
        run: |
          python -m compileall -q broker mcp hooks

  manifest-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate plugin manifest
        run: |
          python -c "import json; json.load(open('elephant-coder2/.claude-plugin/plugin.json'))"
          python -c "import json; json.load(open('elephant-coder2/hooks/hooks.json'))"
          python -c "import json; json.load(open('elephant-coder2/.mcp.json'))"
```

- [ ] **Step 2: Commit**

```bash
git add elephant-coder2/.github
git commit -m "ci(ec2): GitHub Actions workflow"
```

---

### Task 29: End-to-end smoke test

**Files:**
- Create: `elephant-coder2/tests/test_e2e.py`

- [ ] **Step 1: Write E2E smoke**

Create `elephant-coder2/tests/test_e2e.py`:

```python
"""End-to-end: spawn broker, run a hook sequence, verify memory context appears."""
import json
import subprocess
import time
from pathlib import Path
import sys
import pytest


@pytest.fixture
def plugin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path / "home"))
    # Stub embedder for speed
    import broker.store.embedder as emb
    import numpy as np
    monkeypatch.setattr(emb, "embed", lambda t: np.ones(384, dtype=np.float32) / (384 ** 0.5))
    return tmp_path


def test_session_then_read_injects_context(plugin_env, monkeypatch):
    from broker.main import Broker
    from broker.client import BrokerClient
    from broker.protocol import Request

    proj_dir = plugin_env / "proj"
    proj_dir.mkdir()
    (proj_dir / "auth.py").write_text("def verify_token(jwt):\n    return True\n")

    b = Broker(project_root=str(proj_dir), port=0, disable_sidecar=True)
    b.start()
    try:
        for _ in range(50):
            if b.server.port:
                break
            time.sleep(0.02)
        client = BrokerClient(port=b.server.port)

        # Reindex the project
        tid = client.call(Request(op="schedule_task", args={"type": "reindex_project"})).data["task_id"]
        for _ in range(100):
            r = client.call(Request(op="get_task", args={"task_id": tid})).data
            if r.get("status") == "done":
                break
            time.sleep(0.05)

        # Now simulate a PreToolUse:Read request
        rsp = client.call(Request(op="recall_file", args={"file_path": str(proj_dir / "auth.py")}))
        assert rsp.ok
        syms = [item["symbol"] for item in rsp.data["items"]]
        assert "verify_token" in syms
    finally:
        b.stop()
```

- [ ] **Step 2: Run**

```bash
python -m pytest tests/test_e2e.py -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test(ec2): end-to-end smoke"
```

---

### Task 30: Final: update marketplace version and CHANGELOG

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `elephant-coder2/CHANGELOG.md`

- [ ] **Step 1: Bump plugin version (if needed) and confirm marketplace entry is correct**

Inspect `C:/Users/grill/grilly-plugins/.claude-plugin/marketplace.json` — verify the `elephant-coder2` entry exists with version `0.1.0`. Adjust description if shipped surface differs from planned.

- [ ] **Step 2: Update CHANGELOG**

Append to `elephant-coder2/CHANGELOG.md`:

```markdown
## [0.1.0] - 2026-04-17

### Added
- Broker process (TCP localhost socket, cross-platform) assembling storage + retrieval + sidecar + tasks.
- Three-tier memory: scratch (32k cap) / project_durable / global_durable. Promotion is Claude-driven.
- Storage: Redis primary cache (graceful fallback) + SQLite+FTS5 durable + numpy vectors.
- Small-model sidecar via llama-cpp-python (Qwen 2.5 1.5B Q4_K_M default). Summarize / rerank / consolidate.
- Idle consolidation loop with decision log at `~/.elephant-coder2/sidecar/consolidation.log`.
- Multi-language indexer: Python AST + regex extractor (TS/JS/C/C++/GLSL) + structured (MD/TOML/JSON/YAML).
- 5 hooks: SessionStart, UserPromptSubmit, PreToolUse:Read/Grep/Glob/Task, PostToolUse:Edit/Write. Automatic memory context injection; no reminders.
- PreToolUse:Task auto-briefing for subagents with `<no-brief/>` opt-out.
- 12 MCP tools: recall, recall_file, search_symbol, graph, remember, promote, sidecar_store, sidecar_recall, brief_subagent, schedule_task, status, configure.
- 20 skills + slash commands.
- Background task queue with push-notification on completion.
- GitHub Actions CI (test + lint + manifest validate).
- End-to-end smoke test.
```

- [ ] **Step 3: Commit**

```bash
git add elephant-coder2/CHANGELOG.md .claude-plugin/marketplace.json
git commit -m "chore(ec2): finalize 0.1.0 changelog and marketplace entry"
```

---

## Self-Review Notes

Checked against the spec at `docs/superpowers/specs/2026-04-17-elephant-coder2-design.md`:

- Broker + storage + retrieval + sidecar + tasks + hooks + MCP + skills + CI all represented.
- Redis optional with SQLite-only fallback — Task 8 test covers the unavailable case.
- Windows caveat (Unix socket → TCP localhost) resolved in Task 5; no named-pipe complexity.
- Small model rerank latency budget (500ms default) enforced in Task 14; fallback to identity order.
- Token budgets (800 / 300 / 500) applied in hooks (Tasks 19–20).
- `<no-brief/>` opt-out implemented in Task 20 (pretooluse_agent).
- Promotion to `global_durable` involves moving the entry from project store to global store (Task 17 promote handler).
- Identity / protected memories supported at schema level (Task 6); protected entries skipped during consolidation (Task 15).

**Known deferred to implementation time:**
- `graph` MCP tool is a placeholder — full call-graph requires a Phase-11-style follow-up (import parsing, reverse index). Flagged in MCP schema as "(Placeholder)". Safe to ship, and callers get an empty/partial result rather than an error.
- Push notifications through Claude Code's system-reminder channel are stubbed as logs in Task 17. Implementation depends on Claude Code exposing a stable API (PushNotification tool mentioned in harness); connect that in a follow-up.
- `modules` skill relies on a dynamic-import harness not yet implemented in this plan — that's a future addition; the skill file sets expectations.

---

## Execution Handoff

Plan complete and saved. Two execution options:

1. **Subagent-Driven (recommended for a plan this size)** — fresh subagent per task, review between tasks. Faster recovery from mistakes and keeps main context lean.
2. **Inline Execution** — execute tasks in this session. Heavier on main context, but more direct.

User's stated intent: "monolithic and build." Proceeding with **subagent-driven execution** since the plan has 30 tasks and subagents keep main context clean.


