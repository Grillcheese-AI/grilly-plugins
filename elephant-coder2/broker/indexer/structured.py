"""Indexers for markdown / toml / json / yaml / cmake."""
from __future__ import annotations

import re

from broker.store.sqlite_store import MemoryEntry
from .python_ast import _keywords_for, _summary


def index_markdown(source: str, file_path: str, file_mtime: float) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    sections = re.split(r"(?m)^(#{1,6}\s+.+)$", source)
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
