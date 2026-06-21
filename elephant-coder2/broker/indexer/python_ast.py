"""Python AST-based indexer: extracts functions, classes, methods, module docstring."""
from __future__ import annotations

import ast
import re

from broker.store.sqlite_store import MemoryEntry


def _name_tokens(name: str) -> list[str]:
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
    lines = (doc or "").strip().splitlines()      # whitespace-only doc -> [] (not [0] IndexError)
    first = lines[0] if lines else ""
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
