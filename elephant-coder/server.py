"""
Elephant-Coder MCP Server — persistent codebase memory for Claude Code.

Inspired by the hippocampal memory circuit in grilly/nn/hippocampal.py:
- Capsule encoding: compress source files into compact AST summaries
- DG pattern separation: extract discriminative keywords for FTS5 indexing
- CA3 pattern completion: retrieve full context from partial queries
- Cognitive metadata: track access frequency, relevance, freshness
- Consolidation: evict stale/low-relevance memories, keep capacity bounded

Register with Claude Code:
    claude mcp add --transport stdio elephant-coder -- python server.py
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from consolidator import consolidate, detect_stale, should_consolidate
from indexer import index_file
from mcp.server.fastmcp import FastMCP
from memory_store import MemoryEntry, MemoryStore, make_memory_id
from retriever import format_results, recall, recall_file

# Logging to stderr only (stdout reserved for MCP stdio transport)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("elephant-coder")

# ------------------------------------------------------------------
# Server setup
# ------------------------------------------------------------------

mcp = FastMCP("elephant-coder")

# Lazy-initialized store (needs project root at first tool call)
_store: MemoryStore | None = None

# Redis URL from CLI arg or env var
_redis_url: str | None = None


def _get_store() -> MemoryStore:
    """Get or initialize the memory store for the current project."""
    global _store
    if _store is None:
        project_root = _detect_project_root()
        _store = MemoryStore(project_root, redis_url=_redis_url)
        logger.info("Memory store initialized for project: %s", project_root)
    return _store


def _detect_project_root() -> str:
    """Walk up from cwd to find a project root (has .git or pyproject.toml)."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return str(parent)
    return str(cwd)


def _normalize_path(path: str) -> str:
    """Resolve a path relative to project root if not absolute."""
    p = Path(path)
    if not p.is_absolute():
        root = _detect_project_root()
        p = Path(root) / p
    return str(p.resolve())


# ------------------------------------------------------------------
# MCP Tools
# ------------------------------------------------------------------


@mcp.tool()
def remember(
    file_path: str,
    symbol_name: str,
    summary: str,
    kind: str = "note",
    keywords: list[str] | None = None,
) -> str:
    """Store a memory about code you have explored or understood.

    Call this after reading and understanding a file or function to save
    a compressed summary for future retrieval. This avoids re-reading
    the same code in future conversations.

    Args:
        file_path: Path to the source file this memory relates to
        symbol_name: Name of the function, class, or concept
        summary: Compressed summary of what this code does
        kind: One of "function", "class", "module", "file_summary", "note"
        keywords: Optional list of search keywords
    """
    store = _get_store()
    fp = _normalize_path(file_path)

    try:
        mtime = os.path.getmtime(fp)
    except OSError:
        mtime = 0.0

    entry = MemoryEntry(
        memory_id=make_memory_id(fp, symbol_name, kind),
        file_path=fp,
        symbol_name=symbol_name,
        kind=kind,
        summary=summary,
        keywords=keywords or [],
        file_mtime=mtime,
    )
    store.upsert(entry)
    return f"Remembered: {kind} '{symbol_name}' in {file_path} (id: {entry.memory_id})"


@mcp.tool()
def recall_memories(query: str, limit: int = 5, kind: str | None = None) -> str:
    """Retrieve relevant memories about the codebase.

    Search stored memories using full-text search. Returns compressed
    summaries so you don't need to re-read the full source files.
    Call this before reading files to check if you already have context.

    Args:
        query: Search query (keywords, function names, concepts)
        limit: Maximum number of results to return (default 5)
        kind: Optional filter by kind ("function", "class", "module", etc.)
    """
    store = _get_store()
    results = recall(store, query, limit=limit, kind=kind)
    return format_results(results)


@mcp.tool()
def recall_file_memories(file_path: str) -> str:
    """Retrieve all memories about a specific file.

    Returns all stored summaries for functions, classes, and the module
    summary for the given file. Useful to get an overview before diving
    into the file.

    Args:
        file_path: Path to the file to recall memories about
    """
    store = _get_store()
    fp = _normalize_path(file_path)
    results = recall_file(store, fp)
    if not results:
        return f"No memories stored for {file_path}. Use index_directory or remember to add some."
    return format_results(results)


@mcp.tool()
def index_directory(
    path: str = ".",
    patterns: str = "**/*.py",
    max_files: int = 20000,
    force: bool = False,
) -> str:
    """Index source files in a directory, extracting function/class summaries.

    Walks the directory, parses each file, and stores compressed
    summaries of every function, class, and module. Automatically skips
    files that haven't changed since last indexing (use force=True to re-index all).

    Supports: Python (.py), TypeScript/JavaScript (.ts/.js/.tsx/.jsx),
    C/C++ (.c/.cpp/.cc/.cxx/.h/.hpp/.hxx), GLSL shaders (.glsl/.vert/.frag/.comp),
    Markdown (.md), PDF (.pdf), TOML (.toml), JSON (.json), YAML (.yaml/.yml),
    CMake (CMakeLists.txt/.cmake).

    Args:
        path: Directory path to index (default: current directory)
        patterns: Glob pattern for files to include (default: **/*.py)
        max_files: Maximum number of files to index in one call
        force: If True, re-index all files even if unchanged (default: False)
    """
    store = _get_store()
    dir_path = Path(_normalize_path(path))

    if not dir_path.is_dir():
        return f"Error: {path} is not a directory."

    # Collect matching files
    files = sorted(dir_path.glob(patterns))
    # Skip common non-source directories
    skip_dirs = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        ".eggs",
        "htmlcov",
        "third_party",
    }
    # Prefixes that match directories starting with these strings (e.g. build, build312)
    skip_prefixes = ("build", ".egg-info")

    def _should_skip(filepath: Path) -> bool:
        for part in filepath.parts:
            if part in skip_dirs:
                return True
            if any(part.startswith(p) or part.endswith(p) for p in skip_prefixes):
                return True
        return False

    files = [f for f in files if f.is_file() and not _should_skip(f)]
    files = files[:max_files]

    t0 = time.time()
    total_symbols = 0
    indexed_files = 0
    skipped_files = 0

    for fpath in files:
        try:
            fp_str = str(fpath)

            # Smart mtime check — skip unchanged files
            if not force:
                try:
                    actual_mtime = os.path.getmtime(fp_str)
                    existing = store.search_by_file(fp_str)
                    if existing and all(
                        e.file_mtime >= actual_mtime for e in existing
                    ):
                        skipped_files += 1
                        continue
                except OSError:
                    pass

            entries = index_file(fp_str)
            for entry in entries:
                store.upsert(entry)
            total_symbols += len(entries)
            indexed_files += 1
        except Exception as exc:
            logger.warning("Failed to index %s: %s", fpath, exc)

    elapsed = time.time() - t0

    # Auto-consolidate if near capacity
    if should_consolidate(store):
        cstats = consolidate(store)
        logger.info("Auto-consolidation: %s", cstats)

    result = f"Indexed {indexed_files} files, {total_symbols} symbols in {elapsed:.1f}s"
    if skipped_files:
        result += f"\nSkipped {skipped_files} unchanged files"
    result += f"\nTotal memories: {store.count()}/{store.max_memories}"
    return result


@mcp.tool()
def explore_structure(path: str = ".", max_depth: int = 3) -> str:
    """Explore and summarize the directory structure of a codebase.

    Walks the directory tree and returns a structured overview including
    file counts per directory and identified patterns (tests, configs, etc.).

    Args:
        path: Root directory to explore (default: current directory)
        max_depth: Maximum depth to traverse (default: 3)
    """
    dir_path = Path(_normalize_path(path))
    if not dir_path.is_dir():
        return f"Error: {path} is not a directory."

    skip_dirs = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        ".eggs",
        "htmlcov",
        "third_party",
    }
    skip_prefixes = ("build",)

    lines = [f"Project structure: {dir_path.name}/"]
    _walk_tree(dir_path, dir_path, lines, skip_dirs, skip_prefixes, max_depth, depth=0)
    return "\n".join(lines)


def _walk_tree(
    root: Path,
    current: Path,
    lines: list[str],
    skip_dirs: set[str],
    skip_prefixes: tuple[str, ...],
    max_depth: int,
    depth: int,
) -> None:
    """Recursively build directory tree with file counts."""
    if depth > max_depth:
        return

    indent = "  " * depth
    try:
        entries = sorted(current.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    except PermissionError:
        return

    dirs = [
        e for e in entries
        if e.is_dir() and e.name not in skip_dirs
        and not any(e.name.startswith(p) for p in skip_prefixes)
    ]
    files = [e for e in entries if e.is_file()]

    # Summarize files by extension
    ext_counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix or "(no ext)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    if ext_counts and depth > 0:
        summary = ", ".join(f"{c} {ext}" for ext, c in sorted(ext_counts.items()))
        lines.append(f"{indent}{current.name}/  [{summary}]")
    elif depth > 0:
        lines.append(f"{indent}{current.name}/")

    for d in dirs:
        _walk_tree(root, d, lines, skip_dirs, skip_prefixes, max_depth, depth + 1)


@mcp.tool()
def search_symbols(name: str, kind: str | None = None) -> str:
    """Search for symbols by name (faster than FTS for exact matches).

    Direct symbol lookup by name with optional kind filter. Tries exact
    match first, then prefix match.

    Args:
        name: Symbol name to search for (function, class, module name)
        kind: Optional filter by kind ("function", "class", "module", etc.)
    """
    store = _get_store()
    results = store.search_by_symbol(name, kind=kind)
    if not results:
        return f"No symbols found matching '{name}'."
    return format_results(results)


@mcp.tool()
def get_dependencies(file_path: str) -> str:
    """Show what a file imports and what imports it.

    Returns the import relationships for a file: what modules it depends on,
    and what other indexed files depend on it.

    Args:
        file_path: Path to the file to analyze dependencies for
    """
    store = _get_store()
    fp = _normalize_path(file_path)
    deps = store.get_dependencies(fp)

    lines = [f"Dependencies for {Path(fp).name}:"]
    lines.append("")
    if deps["imports"]:
        lines.append("  Imports:")
        for imp in deps["imports"]:
            lines.append(f"    - {imp}")
    else:
        lines.append("  Imports: (none indexed)")

    lines.append("")
    if deps["imported_by"]:
        lines.append("  Imported by:")
        for f in deps["imported_by"]:
            lines.append(f"    - {Path(f).name}  ({f})")
    else:
        lines.append("  Imported by: (none found)")

    return "\n".join(lines)


@mcp.tool()
def forget(
    query: str | None = None,
    file_path: str | None = None,
    stale_only: bool = False,
) -> str:
    """Remove memories. Use to clear stale or irrelevant context.

    Args:
        query: Remove memories matching this search query
        file_path: Remove all memories for this file path
        stale_only: If True, only remove memories whose files have changed on disk
    """
    store = _get_store()

    if stale_only:
        detect_stale(store)
        count = store.delete_stale()
        return f"Removed {count} stale memories."

    if file_path:
        fp = _normalize_path(file_path)
        count = store.delete_by_file(fp)
        return f"Removed {count} memories for {file_path}."

    if query:
        results = store.search_fts(query, limit=100)
        count = 0
        for entry in results:
            if store.delete(entry.memory_id):
                count += 1
        return f"Removed {count} memories matching '{query}'."

    return "Specify query, file_path, or stale_only=True."


@mcp.tool()
def memory_status() -> str:
    """Get statistics about the memory store.

    Returns total memories, breakdown by kind, staleness status,
    most accessed memories, and storage utilization.
    """
    store = _get_store()

    # Detect staleness before reporting
    detect_stale(store)

    s = store.stats()
    lines = [
        "Memory Store Status",
        f"  Total: {s['total']}/{s['max_capacity']} ({s['utilization_pct']}% utilized)",
        f"  Stale: {s['stale']}",
        f"  Redis: {'connected' if s['redis_connected'] else 'not connected'}",
        "",
        "  By kind:",
    ]
    for kind, count in sorted(s["by_kind"].items()):
        lines.append(f"    {kind}: {count}")

    if s["top_accessed"]:
        lines.append("")
        lines.append("  Most accessed:")
        for item in s["top_accessed"]:
            lines.append(f"    {item['symbol']} ({item['file']}) — {item['count']}x")

    return "\n".join(lines)


@mcp.tool()
def ingest_knowledge(
    path: str = "docs/project_knowledge",
    max_files: int = 100,
    force: bool = False,
) -> str:
    """Ingest documents from a knowledge directory into memory.

    Reads all supported files (PDF, Markdown, TOML, JSON, YAML, text)
    from the given directory and stores their content as searchable memories.
    Use this to load project papers, design docs, or reference materials.

    Default paths:
    - docs/official_papers — published research papers
    - docs/project_knowledge — uploaded reference documents

    Args:
        path: Directory containing documents to ingest (default: docs/project_knowledge)
        max_files: Maximum files to process (default: 100)
        force: Re-ingest even if unchanged (default: False)
    """
    store = _get_store()
    dir_path = Path(_normalize_path(path))

    if not dir_path.is_dir():
        return f"Error: {path} is not a directory. Create it first."

    # Supported document extensions
    doc_extensions = {".pdf", ".md", ".txt", ".toml", ".json", ".yaml", ".yml",
                      ".tex", ".rst", ".csv", ".log"}

    files = []
    for f in sorted(dir_path.rglob("*")):
        if f.is_file() and f.suffix.lower() in doc_extensions:
            files.append(f)
    files = files[:max_files]

    if not files:
        return f"No supported documents found in {path}."

    t0 = time.time()
    total_symbols = 0
    indexed_files = 0
    skipped_files = 0

    for fpath in files:
        try:
            fp_str = str(fpath)

            # Smart mtime check
            if not force:
                try:
                    actual_mtime = os.path.getmtime(fp_str)
                    existing = store.search_by_file(fp_str)
                    if existing and all(e.file_mtime >= actual_mtime for e in existing):
                        skipped_files += 1
                        continue
                except OSError:
                    pass

            entries = index_file(fp_str)

            # For plain text files (.txt, .tex, .rst, .csv, .log), create a manual entry
            if not entries and fpath.suffix.lower() in (".txt", ".tex", ".rst", ".csv", ".log"):
                entries = _index_text_file(fp_str)

            for entry in entries:
                store.upsert(entry)
            total_symbols += len(entries)
            indexed_files += 1
        except Exception as exc:
            logger.warning("Failed to ingest %s: %s", fpath, exc)

    elapsed = time.time() - t0

    result = f"Ingested {indexed_files} documents, {total_symbols} entries in {elapsed:.1f}s"
    if skipped_files:
        result += f"\nSkipped {skipped_files} unchanged files"
    result += f"\nTotal memories: {store.count()}/{store.max_memories}"
    return result


def _index_text_file(file_path: str) -> list[MemoryEntry]:
    """Index a plain text file by chunking into page-sized memories."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    # Split into chunks of ~500 lines
    lines = source.split('\n')
    chunk_size = 500
    chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]

    for i, chunk in enumerate(chunks, 1):
        text = '\n'.join(chunk).strip()
        if not text:
            continue
        preview = text[:500]
        first_line = chunk[0].strip()[:80] if chunk else f"chunk_{i}"

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, f"chunk_{i}", "note"),
            file_path=file_path,
            symbol_name=f"chunk_{i}: {first_line}" if first_line else f"chunk_{i}",
            kind="note",
            summary=preview,
            keywords=_extract_text_keywords(preview[:200]),
            file_mtime=file_mtime,
        ))

    # Module entry
    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary=f"Text file: {path.name} ({len(lines)} lines, {len(chunks)} chunks)",
        keywords=_extract_text_keywords(module_name + " " + source[:200]),
        line_count=len(lines),
        file_mtime=file_mtime,
    ))

    return entries


def _extract_text_keywords(text: str) -> list[str]:
    """Extract keywords from plain text (for non-code files)."""
    import re
    tokens: set[str] = set()
    # Split on whitespace and punctuation
    parts = re.split(r'[^a-zA-Z0-9]+', text)
    stop = {'the', 'is', 'in', 'of', 'to', 'and', 'or', 'for', 'if', 'not',
            'with', 'as', 'from', 'by', 'on', 'at', 'be', 'it', 'an', 'no',
            'do', 'this', 'that', 'are', 'was', 'were', 'has', 'have', 'had',
            'but', 'we', 'our', 'its', 'can', 'will', 'each', 'which', 'their'}
    for part in parts:
        low = part.lower()
        if len(low) >= 3 and low not in stop:
            tokens.add(low)
    return sorted(tokens)[:30]


@mcp.tool()
def show_call_graph(symbol: str, depth: int = 2) -> str:
    """Show the call graph for a symbol — what it calls and what calls it.

    Traverses the dependency chain to the specified depth, showing
    the tree of function/method calls rooted at the given symbol.

    Args:
        symbol: Symbol name to trace (function, class, or module name)
        depth: Maximum depth to traverse (default: 2)
    """
    store = _get_store()
    results = store.search_by_symbol(symbol)
    if not results:
        # Try FTS fallback
        results = store.search_fts(symbol, limit=5)
    if not results:
        return f"No symbol found matching '{symbol}'."

    lines = [f"Call graph for '{symbol}' (depth={depth}):", ""]

    visited: set[str] = set()

    def _trace(entries: list[MemoryEntry], indent: int, remaining_depth: int, direction: str) -> None:
        for entry in entries:
            if entry.memory_id in visited:
                lines.append(f"{'  ' * indent}  {entry.symbol_name} (circular)")
                continue
            visited.add(entry.memory_id)
            kind_tag = f"[{entry.kind}]"
            fname = Path(entry.file_path).name if entry.file_path else ""
            lines.append(f"{'  ' * indent}{direction} {entry.symbol_name} {kind_tag}  ({fname})")

            if remaining_depth <= 0 or not entry.dependencies:
                continue

            # Resolve dependencies to actual entries
            for dep_name in entry.dependencies[:10]:
                dep_entries = store.search_by_symbol(dep_name)
                if dep_entries:
                    _trace(dep_entries[:1], indent + 1, remaining_depth - 1, "->")

    # Forward trace (what this symbol calls)
    lines.append("Calls:")
    _trace(results[:1], 1, depth, "->")

    # Reverse trace (what calls this symbol)
    visited.clear()
    lines.append("")
    lines.append("Called by:")
    for entry in results[:1]:
        # Search for entries that list this symbol in dependencies
        referencing = store.search_fts(entry.symbol_name, limit=20)
        callers = [
            r for r in referencing
            if r.memory_id != entry.memory_id
            and entry.symbol_name in (r.dependencies or [])
        ]
        if callers:
            _trace(callers[:5], 1, 0, "<-")
        else:
            lines.append("  (no callers found in index)")

    return "\n".join(lines)


@mcp.tool()
def summarize_directory(path: str = ".", max_symbols: int = 50) -> str:
    """Condensed table-of-contents for all indexed symbols in a directory.

    Returns a compact overview of every class, function, and module
    indexed under the given directory. Great for getting oriented.

    Args:
        path: Directory to summarize (default: current directory)
        max_symbols: Maximum symbols to show (default: 50)
    """
    store = _get_store()
    dir_path = _normalize_path(path)

    # Query all memories whose file_path starts with this directory
    rows = store._conn.execute(
        "SELECT * FROM memories WHERE file_path LIKE ? ORDER BY file_path, kind, symbol_name",
        (f"{dir_path}%",),
    ).fetchall()

    if not rows:
        return f"No indexed symbols found under {path}."

    entries = [store._row_to_entry(r) for r in rows]

    # Group by file
    by_file: dict[str, list[MemoryEntry]] = {}
    for e in entries:
        rel = os.path.relpath(e.file_path, dir_path)
        by_file.setdefault(rel, []).append(e)

    lines = [f"Summary of {path} ({len(entries)} symbols across {len(by_file)} files):", ""]
    shown = 0

    for rel_path in sorted(by_file.keys()):
        if shown >= max_symbols:
            lines.append(f"... +{len(entries) - shown} more symbols")
            break
        file_entries = by_file[rel_path]
        # Show line count from module entry if available
        module_entry = next((e for e in file_entries if e.kind == "module"), None)
        lc_tag = f"  [{module_entry.line_count} lines]" if module_entry and module_entry.line_count else ""
        lines.append(f"  {rel_path}{lc_tag}:")
        for e in file_entries:
            if shown >= max_symbols:
                break
            if e.kind == "module":
                continue  # Skip module-level summaries for compactness
            # One-line summary
            summary_line = e.summary.split('\n')[0][:80]
            lines.append(f"    [{e.kind}] {summary_line}")
            shown += 1
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def recent_changes(days: int = 7, limit: int = 20) -> str:
    """Show recently modified symbols based on git history.

    Uses git log to find files changed in the last N days, then
    returns the indexed symbols for those files. Useful for
    understanding what's been worked on recently.

    Args:
        days: Look back this many days (default: 7)
        limit: Maximum number of files to show (default: 20)
    """
    store = _get_store()
    project_root = _detect_project_root()

    try:
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--name-only",
             "--pretty=format:", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode != 0:
            return f"git log failed: {result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"Could not run git: {exc}"

    # Parse changed files (deduplicate, most recent first)
    seen: set[str] = set()
    changed_files: list[str] = []
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        changed_files.append(line)

    if not changed_files:
        return f"No files changed in the last {days} days."

    changed_files = changed_files[:limit]

    lines = [f"Recently changed files (last {days} days):", ""]

    for rel_path in changed_files:
        abs_path = str(Path(project_root) / rel_path)
        file_entries = store.search_by_file(abs_path)

        if file_entries:
            symbols = [e for e in file_entries if e.kind != "module"]
            symbol_names = [e.symbol_name for e in symbols[:5]]
            stale = any(e.is_stale for e in file_entries)
            stale_tag = " [STALE]" if stale else ""
            module_entry = next((e for e in file_entries if e.kind == "module"), None)
            lc_tag = f" [{module_entry.line_count}L]" if module_entry and module_entry.line_count else ""
            if symbol_names:
                lines.append(f"  {rel_path}{lc_tag}{stale_tag}")
                lines.append(f"    Symbols: {', '.join(symbol_names)}")
            else:
                lines.append(f"  {rel_path}{lc_tag}{stale_tag} (module only)")
        else:
            lines.append(f"  {rel_path} (not indexed)")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Elephant-Coder MCP Server")
    parser.add_argument("--redis-url", default=None, help="Redis URL (default: redis://localhost:6380)")
    args = parser.parse_args()

    if args.redis_url:
        _redis_url = args.redis_url

    mcp.run(transport="stdio")
