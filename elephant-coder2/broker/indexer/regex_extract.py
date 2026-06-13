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
