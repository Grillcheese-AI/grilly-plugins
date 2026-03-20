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

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from consolidator import consolidate, detect_stale, should_consolidate
from indexer import index_file
from link_graph import resolve_python_imports, resolve_cpp_includes, detect_shader_dispatches, resolve_module_to_path
from mental_model import generate_mental_model
from framework_detector import detect_frameworks
from mcp.server.fastmcp import FastMCP
from memory_store import MemoryEntry, MemoryStore, make_memory_id
from retriever import format_results, recall, recall_file
from settings import load_settings, save_settings
from task_manager import TaskManager
from scope_guard import check_file_size, check_duplicate_file
from news_reader import fetch_feeds, deduplicate_articles, generate_briefing, fetch_full_article
from research_engine import call_openrouter, build_review_prompt, build_audit_prompt
from global_store import GlobalKnowledgeStore
from vector_store import VectorStore
from user_profile import UserProfile, CATEGORIES
from module_system import ModuleSystem, MODULE_TYPES
from merit_ledger import MeritLedger, MERIT_VALUES, RANKS
from think_tank import ThinkTank, EXECUTIVES, TEMPLATES

# Logging to stderr AND to a file for debugging
_log_file = Path.home() / ".elephant-coder" / "server.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(str(_log_file), encoding="utf-8"),
    ],
)
logger = logging.getLogger("elephant-coder")

# Startup diagnostics
logger.info("CLAUDE_PROJECT_DIR=%s", os.environ.get("CLAUDE_PROJECT_DIR", "NOT SET"))
logger.info("CWD=%s", os.getcwd())
logger.info("Python=%s", sys.executable)
logger.info("Server module=%s", __file__)

# ------------------------------------------------------------------
# Server setup
# ------------------------------------------------------------------

mcp = FastMCP("elephant-coder")

# Per-project store cache — maps project_root -> MemoryStore
_stores: dict[str, MemoryStore] = {}

# Per-project vector store cache
_vector_stores: dict[str, VectorStore] = {}

# Redis URL from CLI arg or env var
_redis_url: str | None = None

# Project root override (set by Claude Code via environment or tool call)
_project_root_override: str | None = None


def _get_store() -> MemoryStore:
    """Get or initialize the memory store for the current project.

    Uses a per-project cache so switching between projects (different
    working directories) doesn't corrupt each other's memory.
    """
    project_root = _detect_project_root()
    if project_root not in _stores:
        settings = load_settings(project_root)
        redis_url = settings.get("redis_url") or _redis_url
        max_mem = settings.get("max_memories", 50_000)
        _stores[project_root] = MemoryStore(project_root, max_memories=max_mem, redis_url=redis_url)
        logger.info("Memory store initialized for project: %s (max: %d)", project_root, max_mem)
    return _stores[project_root]


def _get_vector_store() -> VectorStore | None:
    """Get or initialize the vector store for the current project.

    Returns None if vector search is disabled in settings.
    """
    project_root = _detect_project_root()
    if project_root not in _vector_stores:
        settings = load_settings(project_root)
        vs_settings = settings.get("vector_search", {})
        if not vs_settings.get("enabled", True):
            return None
        qdrant_url = vs_settings.get("qdrant_url")
        try:
            _vector_stores[project_root] = VectorStore(project_root, qdrant_url=qdrant_url)
            logger.info("VectorStore initialized for project: %s (mode: %s)",
                        project_root, _vector_stores[project_root].mode)
        except Exception as exc:
            logger.warning("VectorStore init failed: %s — semantic search disabled", exc)
            return None
    return _vector_stores.get(project_root)


def _detect_project_root() -> str:
    """Detect the project root for the current context.

    Priority:
    1. Explicit override (set by set_project_root tool)
    2. CLAUDE_PROJECT_DIR environment variable (set by Claude Code)
    3. Walk up from cwd to find .git or pyproject.toml
       (but never resolve to the elephant-coder plugin's own directory)
    """
    if _project_root_override:
        return _project_root_override

    # Claude Code sets this env var for multi-workspace setups
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).exists():
        return str(Path(env_root).resolve())

    # Walk up from cwd, but skip the plugin's own directory
    server_dir = str(Path(__file__).resolve().parent)
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if str(parent.resolve()) == server_dir:
            continue  # don't resolve to our own plugin source
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


def _load_settings() -> dict:
    """Load settings for the current project."""
    return load_settings(_detect_project_root())


_task_mgrs: dict[str, TaskManager] = {}

def _get_task_manager() -> TaskManager:
    project_root = _detect_project_root()
    if project_root not in _task_mgrs:
        db_dir = Path.home() / ".elephant-coder" / hashlib.sha256(project_root.encode()).hexdigest()[:12]
        db_dir.mkdir(parents=True, exist_ok=True)
        _task_mgrs[project_root] = TaskManager(str(db_dir))
    return _task_mgrs[project_root]


_global: GlobalKnowledgeStore | None = None

def _get_global_store() -> GlobalKnowledgeStore:
    global _global
    if _global is None:
        _global = GlobalKnowledgeStore()
    return _global


_user_profile: UserProfile | None = None

def _get_user_profile() -> UserProfile | None:
    """Get the global user profile singleton, if opt-in enabled."""
    global _user_profile
    settings = load_settings(_detect_project_root())
    up_settings = settings.get("user_profile", {})
    if not up_settings.get("enabled", False):
        return None
    if _user_profile is None:
        _user_profile = UserProfile()
        logger.info("Global UserProfile loaded from %s", _user_profile._db)
    return _user_profile


_module_systems: dict[str, ModuleSystem] = {}

def _get_module_system() -> ModuleSystem:
    """Get the module system for the current project."""
    project_root = _detect_project_root()
    if project_root not in _module_systems:
        _module_systems[project_root] = ModuleSystem(project_root)
    return _module_systems[project_root]


_merit_ledger: MeritLedger | None = None

def _get_merit_ledger() -> MeritLedger:
    """Get the global merit ledger singleton."""
    global _merit_ledger
    if _merit_ledger is None:
        # Look for merit_ledger.json in project root for sync
        project_root = _detect_project_root()
        json_path = os.path.join(project_root, "merit_ledger.json")
        if not os.path.exists(json_path):
            json_path = None
        _merit_ledger = MeritLedger(json_path=json_path)
    return _merit_ledger


_think_tank: ThinkTank | None = None

def _get_think_tank() -> ThinkTank:
    global _think_tank
    if _think_tank is None:
        _think_tank = ThinkTank()
    return _think_tank


def _get_project_keywords() -> list[str]:
    """Extract keywords that describe the current project's domain.

    Pulls from: project objectives, directory name, pyproject.toml description,
    top indexed module names, and README headings. Used to filter RSS feeds
    and rank news articles by project relevance.
    """
    keywords = []
    project_root = _detect_project_root()
    root_path = Path(project_root)

    # 1. Project name from directory
    keywords.append(root_path.name.lower())

    # 2. Objectives from task manager
    try:
        tm = _get_task_manager()
        for obj in tm.get_objectives():
            # Split objectives into words, keep meaningful ones
            for word in obj.lower().split():
                if len(word) > 3 and word not in ("this", "that", "with", "from", "into", "make", "ensure"):
                    keywords.append(word)
    except Exception:
        pass

    # 3. pyproject.toml — project name, description, keywords
    pyproj = root_path / "pyproject.toml"
    if pyproj.exists():
        try:
            text = pyproj.read_text(encoding="utf-8")
            import re
            # Extract project name
            m = re.search(r'name\s*=\s*"([^"]+)"', text)
            if m:
                keywords.append(m.group(1).lower())
            # Extract description words
            m = re.search(r'description\s*=\s*"([^"]+)"', text)
            if m:
                for word in m.group(1).lower().split():
                    if len(word) > 3:
                        keywords.append(word)
            # Extract explicit keywords
            for m in re.finditer(r'"(\w[\w-]+)"', text):
                kw = m.group(1).lower()
                if len(kw) > 3:
                    keywords.append(kw)
        except Exception:
            pass

    # 4. package.json for JS/TS projects
    pkgjson = root_path / "package.json"
    if pkgjson.exists():
        try:
            import json as _json
            data = _json.loads(pkgjson.read_text())
            if "name" in data:
                keywords.append(data["name"].lower())
            if "description" in data:
                for word in data["description"].lower().split():
                    if len(word) > 3:
                        keywords.append(word)
            for kw in data.get("keywords", []):
                keywords.append(kw.lower())
        except Exception:
            pass

    # 5. Top module names from index (most-connected = most relevant)
    try:
        store = _get_store()
        hubs = store.get_hub_files(limit=5)
        for hub in hubs:
            name = Path(hub["file_path"]).stem.lower()
            if len(name) > 2:
                keywords.append(name)
    except Exception:
        pass

    # Deduplicate and return
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def _extract_and_store_links(store: MemoryStore, fpath: Path, project_root: Path) -> None:
    """Extract imports/includes from a file and store as links."""
    suffix = fpath.suffix.lower()
    fp_str = str(fpath)

    try:
        source = fpath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    store.clear_file_links(fp_str)
    links: list[tuple[str, str, str, str | None]] = []

    if suffix == ".py":
        for module in resolve_python_imports(source):
            resolved = resolve_module_to_path(module, str(project_root), fp_str)
            if resolved:
                links.append((fp_str, resolved, "import", module))
        for shader_name in detect_shader_dispatches(source):
            for shader_ext in [".glsl", ".comp", ".vert", ".frag"]:
                shader_path = project_root / "shaders" / f"{shader_name}{shader_ext}"
                if shader_path.exists():
                    links.append((fp_str, str(shader_path.resolve()), "shader_dispatch", shader_name))
                    break
    elif suffix in (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"):
        for include in resolve_cpp_includes(source):
            for base in [fpath.parent, project_root]:
                candidate = base / include
                if candidate.exists():
                    links.append((fp_str, str(candidate.resolve()), "include", include))
                    break

    if links:
        store.add_file_links_batch(links)


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

    Uses hybrid search: keyword matching (FTS5) + semantic search (vectors).
    Finds results even when query terms don't exactly match code identifiers.
    Call this before reading files to check if you already have context.

    Args:
        query: Search query (keywords, function names, concepts, natural language)
        limit: Maximum number of results to return (default 5)
        kind: Optional filter by kind ("function", "class", "module", etc.)
    """
    store = _get_store()
    settings = _load_settings()
    threshold = settings.get("relevance_threshold", 0.0)
    vs = _get_vector_store()
    results = recall(store, query, limit=limit, kind=kind,
                     relevance_threshold=threshold, vector_store=vs)
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
            if entries:
                store.upsert_batch(entries)
                # Embed for vector search
                vs = _get_vector_store()
                if vs:
                    try:
                        vec_items = [
                            (e.memory_id, f"{e.symbol_name}: {e.summary}", {"kind": e.kind, "file_path": e.file_path})
                            for e in entries
                        ]
                        vs.upsert_batch(vec_items)
                    except Exception as vexc:
                        logger.warning("Vector embedding failed for %s: %s", fpath, vexc)
            total_symbols += len(entries)
            indexed_files += 1
        except Exception as exc:
            logger.warning("Failed to index %s: %s", fpath, exc)

    elapsed = time.time() - t0

    # Auto-consolidate if near capacity
    if should_consolidate(store):
        cstats = consolidate(store)
        logger.info("Auto-consolidation: %s", cstats)

    # Flush vector store
    vs = _get_vector_store()
    if vs:
        vs.flush()

    result = f"Indexed {indexed_files} files, {total_symbols} symbols in {elapsed:.1f}s"
    if skipped_files:
        result += f"\nSkipped {skipped_files} unchanged files"
    result += f"\nTotal memories: {store.count()}/{store.max_memories}"
    return result


_ALL_PATTERNS = [
    "**/*.py", "**/*.ts", "**/*.js", "**/*.tsx", "**/*.jsx",
    "**/*.cpp", "**/*.c", "**/*.h", "**/*.hpp", "**/*.hxx", "**/*.cc", "**/*.cxx",
    "**/*.glsl", "**/*.vert", "**/*.frag", "**/*.comp",
    "**/*.md", "**/*.toml", "**/*.json", "**/*.yaml", "**/*.yml",
    "**/CMakeLists.txt", "**/*.cmake",
]


@mcp.tool()
def index_all(force: bool = False) -> str:
    """Index the entire project — all supported file types in one call.

    Replaces the need to call index_directory() multiple times with
    different patterns. Uses batch upserts for performance. Automatically
    skips unchanged files unless force=True.

    This is the recommended way to index. Called automatically at session start.

    Args:
        force: If True, re-index all files even if unchanged (default: False)
    """
    store = _get_store()
    settings = _load_settings()
    dir_path = Path(_detect_project_root())
    skip_dirs = set(settings.get("skip_dirs", []))

    t0 = time.time()
    total_symbols = 0
    indexed_files = 0
    skipped_files = 0

    for pattern in _ALL_PATTERNS:
        files = sorted(dir_path.glob(pattern))
        files = [f for f in files if f.is_file() and not any(part in skip_dirs for part in f.parts)]

        for fpath in files:
            try:
                fp_str = str(fpath)
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
                if entries:
                    store.upsert_batch(entries)
                    _extract_and_store_links(store, fpath, dir_path)
                    # Embed for vector search
                    vs = _get_vector_store()
                    if vs:
                        try:
                            vec_items = [
                                (e.memory_id, f"{e.symbol_name}: {e.summary}", {"kind": e.kind, "file_path": e.file_path})
                                for e in entries
                            ]
                            vs.upsert_batch(vec_items)
                        except Exception as vexc:
                            logger.warning("Vector embedding failed for %s: %s", fpath, vexc)
                    total_symbols += len(entries)
                indexed_files += 1
            except Exception as exc:
                logger.warning("Failed to index %s: %s", fpath, exc)

    elapsed = time.time() - t0
    if should_consolidate(store):
        cstats = consolidate(store)
        logger.info("Auto-consolidation: %s", cstats)

    # Flush vector store
    vs = _get_vector_store()
    if vs:
        vs.flush()

    result = f"Indexed {indexed_files} files, {total_symbols} symbols in {elapsed:.1f}s"
    if skipped_files:
        result += f"\nSkipped {skipped_files} unchanged files"
    result += f"\nTotal memories: {store.count()}/{store.max_memories}"
    return result


@mcp.tool()
def update_settings(
    max_memories: int | None = None,
    relevance_threshold: float | None = None,
    redis_url: str | None = None,
    skip_dirs: list[str] | None = None,
    scope_guard: bool | None = None,
    auto_test_after_edit: bool | None = None,
    qdrant_url: str | None = None,
    vector_search_enabled: bool | None = None,
    framework: str | None = None,
    github_repo: str | None = None,
    knowledge_docs_path: str | None = None,
    business_docs_path: str | None = None,
    openrouter_api_key: str | None = None,
    external_model: str | None = None,
    external_validation_enabled: bool | None = None,
    rss_feeds: list[str] | None = None,
    rss_enabled: bool | None = None,
    user_profile_enabled: bool | None = None,
) -> str:
    """Update elephant-coder settings for this project.

    Writes to .claude/elephant-coder.local.md. Changes take effect
    on next tool call (settings are re-read).

    Args:
        max_memories: Maximum memories in the store (default: 50000)
        relevance_threshold: Minimum relevance score for search results (default: 0.1)
        redis_url: Redis URL (default: redis://localhost:6379)
        skip_dirs: Directories to skip during indexing
        scope_guard: Enable scope guard (block untracked changes)
        auto_test_after_edit: Prompt to run tests after edits
        qdrant_url: Qdrant URL for vector search (None = local numpy fallback)
        vector_search_enabled: Enable/disable vector semantic search
        framework: Project framework (e.g. "grilly", "django", "react")
        github_repo: GitHub repository (e.g. "grillcheese/elephant-coder")
        knowledge_docs_path: Path for knowledge documents (default: docs/project_knowledge)
        business_docs_path: Path for business documents (default: docs/business)
        openrouter_api_key: OpenRouter API key for external validation
        external_model: External model for validation (e.g. "google/gemini-3.1-flash-lite-preview")
        external_validation_enabled: Enable/disable external validation (ensemble mode)
        rss_feeds: List of RSS feed URLs (replaces current list)
        rss_enabled: Enable/disable RSS news briefing
    """
    current = _load_settings()
    if max_memories is not None:
        current["max_memories"] = max_memories
    if relevance_threshold is not None:
        current["relevance_threshold"] = relevance_threshold
    if redis_url is not None:
        current["redis_url"] = redis_url
    if skip_dirs is not None:
        current["skip_dirs"] = skip_dirs
    if scope_guard is not None:
        current["scope_guard"] = scope_guard
    if auto_test_after_edit is not None:
        current["auto_test_after_edit"] = auto_test_after_edit

    # Vector search settings
    if qdrant_url is not None:
        current.setdefault("vector_search", {})["qdrant_url"] = qdrant_url
    if vector_search_enabled is not None:
        current.setdefault("vector_search", {})["enabled"] = vector_search_enabled

    # Project settings
    if framework is not None:
        current.setdefault("project", {})["framework"] = framework
    if github_repo is not None:
        current.setdefault("project", {})["github_repo"] = github_repo
    if knowledge_docs_path is not None:
        current.setdefault("project", {})["knowledge_docs_path"] = knowledge_docs_path
    if business_docs_path is not None:
        current.setdefault("project", {})["business_docs_path"] = business_docs_path

    # External validation settings
    if openrouter_api_key is not None:
        current.setdefault("external_validation", {})["openrouter_api_key"] = openrouter_api_key
    if external_model is not None:
        current.setdefault("external_validation", {})["model"] = external_model
    if external_validation_enabled is not None:
        current.setdefault("external_validation", {})["enabled"] = external_validation_enabled

    # RSS settings
    if rss_feeds is not None:
        current["rss_feeds"] = rss_feeds
    if rss_enabled is not None:
        if not rss_enabled:
            current["rss_feeds"] = []
        elif not current.get("rss_feeds"):
            # Restore defaults
            from settings import DEFAULT_SETTINGS
            current["rss_feeds"] = DEFAULT_SETTINGS["rss_feeds"]

    # User profile
    if user_profile_enabled is not None:
        current.setdefault("user_profile", {})["enabled"] = user_profile_enabled

    path = save_settings(_detect_project_root(), current)
    return f"Settings updated and saved to {path}"


@mcp.tool()
def project_overview() -> str:
    """Generate a comprehensive project mental model.

    Returns the project's architecture, key files, hub nodes (most-imported files),
    recent changes, and framework detection. Called automatically at session start
    to give Claude immediate project context.
    """
    store = _get_store()
    project_root = _detect_project_root()
    model = generate_mental_model(store, project_root)

    # Framework detection
    frameworks = detect_frameworks(project_root)
    if frameworks:
        model += "\n### Detected Frameworks\n"
        for fw in frameworks:
            model += f"\n- **{fw['name']}** ({fw['detected_as']})"
            if fw.get("github"):
                model += f" — {fw['github']}"
        model += "\n"

    return model


@mcp.tool()
def what_broke(since: str = "1 day ago") -> str:
    """Show what changed semantically since the last session.

    Compares current file state against indexed memories to find
    files that changed. For each changed file, shows what symbols
    were affected and which other files depend on them.

    Args:
        since: Git time expression (default: "1 day ago")
    """
    store = _get_store()
    project_root = _detect_project_root()

    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--name-only", "--pretty=format:", "--diff-filter=ACMR"],
            capture_output=True, text=True, cwd=project_root, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"Could not run git: {exc}"

    if result.returncode != 0:
        return f"git log failed: {result.stderr.strip()}"

    changed_files = list(dict.fromkeys(f.strip() for f in result.stdout.strip().split('\n') if f.strip()))
    if not changed_files:
        return f"No files changed since {since}."

    lines = [f"## What Changed (since {since})", ""]

    for rel_path in changed_files[:20]:
        abs_path = str(Path(project_root) / rel_path)
        file_entries = store.search_by_file(abs_path)
        inbound = store.get_inbound_links(abs_path)

        symbols = [e.symbol_name for e in file_entries if e.kind != "module"][:5]
        stale = any(e.is_stale for e in file_entries)

        line = f"- **{rel_path}**"
        if stale:
            line += " [STALE]"
        if symbols:
            line += f": {', '.join(symbols)}"
        lines.append(line)

        if inbound:
            dependents = [os.path.relpath(l["source_path"], project_root) for l in inbound[:5]]
            lines.append(f"  Impact: {len(inbound)} files depend on this ({', '.join(dependents)})")

    return "\n".join(lines)


@mcp.tool()
def get_tasks() -> str:
    """Get the current project task list with objectives and status."""
    return _get_task_manager().format_task_list()

@mcp.tool()
def add_task(description: str, scope: str = "", priority: str = "medium") -> str:
    """Add a new task to the project task list.

    Args:
        description: What needs to be done
        scope: Comma-separated file paths/directories this task covers
        priority: low, medium, or high
    """
    tm = _get_task_manager()
    scope_list = [s.strip() for s in scope.split(",") if s.strip()] if scope else []
    tid = tm.add_task(description, scope=scope_list, priority=priority)
    return f"Task {tid} created: {description}"

@mcp.tool()
def update_task(task_id: str, status: str = "", notes: str = "") -> str:
    """Update a task's status or notes.

    Args:
        task_id: Task ID (e.g., T-001)
        status: pending, in_progress, or completed
        notes: Additional notes
    """
    tm = _get_task_manager()
    s = status if status else None
    n = notes if notes else None
    if tm.update_task(task_id, status=s, notes=n):
        return f"Task {task_id} updated."
    return f"Task {task_id} not found."

@mcp.tool()
def set_project_objectives(objectives: str) -> str:
    """Set the project's main objectives.

    Args:
        objectives: Pipe-separated list (e.g., "Build GPU framework|PyTorch API compatibility")
    """
    tm = _get_task_manager()
    obj_list = [o.strip() for o in objectives.split("|") if o.strip()]
    tm.set_objectives(obj_list)
    return f"Set {len(obj_list)} objectives."


@mcp.tool()
def get_news_briefing(topics: str = "") -> str:
    """Fetch today's news from configured RSS feeds.

    Reads feeds, follows links to full articles when needed,
    stores new articles as research notes, returns a briefing.
    Called automatically at session start.

    Args:
        topics: Optional comma-separated topic filter
    """
    settings = _load_settings()
    feeds = settings.get("rss_feeds", [])
    if not feeds:
        return "No RSS feeds configured in settings."

    max_per = settings.get("rss_max_articles_per_feed", 5)
    articles = fetch_feeds(feeds, max_per_feed=max_per)

    # Deduplicate against stored notes
    gstore = _get_global_store()
    existing = set()
    for note in gstore.search_notes("", limit=500):
        if note.get("source"):
            existing.add(note["source"])
    articles = deduplicate_articles(articles, existing)

    # Fetch full articles if configured
    if settings.get("rss_fetch_full_articles", True):
        for article in articles:
            if len(article.get("summary", "")) < 200:
                try:
                    full = fetch_full_article(article["link"])
                    if full and len(full) > len(article.get("summary", "")):
                        article["summary"] = full
                except Exception:
                    pass

    # Store as research notes
    for article in articles:
        gstore.save_note(
            topic=article.get("title", "Untitled"),
            summary=article.get("summary", ""),
            source=article.get("link", ""),
            tags=[article.get("source_feed", "news"), "rss"],
        )

    # Auto-detect project-relevant topics from objectives + indexed keywords
    project_keywords = _get_project_keywords()
    if topics:
        project_keywords.extend([t.strip().lower() for t in topics.split(",")])

    if project_keywords:
        # Score articles by project relevance
        relevant = []
        general = []
        for a in articles:
            text = (a.get("title", "") + " " + a.get("summary", "")).lower()
            score = sum(1 for kw in project_keywords if kw in text)
            if score > 0:
                a["_relevance"] = score
                relevant.append(a)
            else:
                general.append(a)
        # Sort relevant by score descending
        relevant.sort(key=lambda x: x.get("_relevance", 0), reverse=True)
        articles = relevant + general

    return generate_briefing(articles)


@mcp.tool()
def take_note(topic: str, summary: str, source: str = "", tags: str = "") -> str:
    """Save a research note for future reference.

    Use when you find something interesting — papers, techniques,
    ideas, patterns. Notes persist across sessions.

    Args:
        topic: Brief topic name
        summary: What you learned
        source: Where you found it (URL, paper ID, etc.)
        tags: Comma-separated tags
    """
    gstore = _get_global_store()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    note_id = gstore.save_note(topic=topic, summary=summary, source=source, tags=tag_list)
    return f"Note saved (id: {note_id}): {topic}"


@mcp.tool()
def recall_notes(query: str, limit: int = 10) -> str:
    """Search your research notes.

    Args:
        query: Search keywords
        limit: Max results
    """
    gstore = _get_global_store()
    notes = gstore.search_notes(query, limit=limit)
    if not notes:
        return f"No notes found for '{query}'."
    lines = [f"## Research Notes ({len(notes)} results)", ""]
    for n in notes:
        tags = ", ".join(n.get("tags", []))
        lines.append(f"**{n['topic']}** [{tags}]")
        lines.append(f"  {n['summary'][:200]}")
        if n.get("source"):
            lines.append(f"  Source: {n['source']}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def get_external_review(plan: str, context: str = "") -> str:
    """Get an adversarial review from an external model via OpenRouter.

    Sends the plan to Gemini 3.1 Flash Lite for independent review.
    Requires external_validation.enabled=true and an OpenRouter API key.

    Args:
        plan: The plan text to review
        context: Additional context (objectives, constraints)
    """
    settings = _load_settings()
    ev = settings.get("external_validation", {})
    if not ev.get("enabled"):
        return "External validation is disabled. Enable in settings."
    api_key = ev.get("openrouter_api_key")
    if not api_key:
        return "No OpenRouter API key configured. Set external_validation.openrouter_api_key in settings or OPENROUTER_API_KEY env var."
    model = ev.get("model", "google/gemini-3.1-flash-lite-preview")
    objectives = context.split("|") if context else []
    try:
        result = call_openrouter(
            build_review_prompt(plan, objectives, []),
            api_key, model)
        return f"## External Review ({result['model']})\n\n{result['review']}"
    except Exception as exc:
        return f"External review failed: {exc}"


@mcp.tool()
def request_audit(task_id: str, files_changed: str = "", test_results: str = "") -> str:
    """Request an independent audit of completed work.

    Args:
        task_id: Task ID that was completed
        files_changed: Summary of files changed
        test_results: Test output
    """
    settings = _load_settings()
    ev = settings.get("external_validation", {})
    if not ev.get("enabled"):
        return "External validation is disabled."
    api_key = ev.get("openrouter_api_key")
    if not api_key:
        return "No OpenRouter API key configured."
    model = ev.get("model", "google/gemini-3.1-flash-lite-preview")
    tm = _get_task_manager()
    task = tm.get_task(task_id)
    task_desc = task["description"] if task else task_id
    files = [f.strip() for f in files_changed.split(",") if f.strip()]
    try:
        result = call_openrouter(
            build_audit_prompt(task_desc, files, test_results),
            api_key, model)
        return f"## Audit ({result['model']})\n\n{result['review']}"
    except Exception as exc:
        return f"Audit failed: {exc}"


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

    # Vector store stats
    vs = _get_vector_store()
    if vs:
        vs_stats = vs.stats()
        lines.append("")
        lines.append("  Vector search:")
        lines.append(f"    Mode: {vs_stats['mode']}")
        lines.append(f"    Encoder: {vs_stats['encoder']} ({vs_stats['dim']}d)")
        lines.append(f"    Local vectors: {vs_stats['local_vectors']}")
        if "qdrant_project_vectors" in vs_stats:
            lines.append(f"    Qdrant project: {vs_stats['qdrant_project_vectors']}")
            lines.append(f"    Qdrant total: {vs_stats['qdrant_total_vectors']}")

    # User profile stats
    up = _get_user_profile()
    if up:
        up_stats = up.stats()
        lines.append("")
        lines.append("  User profile:")
        lines.append(f"    Observations: {up_stats['total_observations']}")
        for cat, info in sorted(up_stats["by_category"].items()):
            lines.append(f"      {cat}: {info['count']} (avg conf: {info['avg_confidence']})")
        lines.append(f"    Request patterns: {up_stats['request_patterns']} ({up_stats['auto_eligible_patterns']} auto-eligible)")

    # Merit stats
    try:
        ml = _get_merit_ledger()
        rank = ml.get_rank()
        lines.append("")
        lines.append(f"  Merits: {rank['total_points']} pts — {rank['rank']}")
        lines.append(f"    Next: {rank['next_rank']} ({rank['points_to_next']} pts away)")
    except Exception:
        pass

    return "\n".join(lines)


# ------------------------------------------------------------------
# User Profile Tools (opt-in)
# ------------------------------------------------------------------

@mcp.tool()
def observe_user(
    category: str,
    content: str,
    confidence: float = 0.5,
    context: str = "",
) -> str:
    """Record an observation about the user's behavior, emotions, or preferences.

    Call this silently when you notice patterns in the user's behavior.
    Do NOT announce observations to the user — just record them.
    Repeated observations automatically increase confidence.

    Categories: emotion, habit, problem, victory, preference,
    recurrent_request, personality, expertise, growth.

    Args:
        category: Type of observation (see categories above)
        content: The observation itself (concise, factual)
        confidence: How confident you are (0.0-1.0, default 0.5)
        context: What triggered this observation
    """
    up = _get_user_profile()
    if up is None:
        return "User profile is not enabled. Enable with: update_settings(user_profile_enabled=True)"
    if category not in CATEGORIES:
        return f"Invalid category '{category}'. Valid: {', '.join(CATEGORIES.keys())}"

    obs = up.observe(category, content, confidence=confidence, context=context)
    return (f"Observed ({obs.category}): {obs.content} "
            f"[confidence: {obs.confidence:.2f}, seen: {obs.frequency}x]")


@mcp.tool()
def record_user_request(
    pattern: str,
    example: str,
    suggested_action: str | None = None,
) -> str:
    """Record a recurrent request pattern from the user.

    When a pattern is seen 3+ times, it becomes a candidate for automation —
    Claude can proactively perform the action before the user asks.

    Args:
        pattern: Generalized request pattern (e.g. "run tests after editing")
        example: The specific instance that triggered this (e.g. "run pytest")
        suggested_action: What Claude should do automatically
    """
    up = _get_user_profile()
    if up is None:
        return "User profile is not enabled."

    result = up.record_request(pattern, example, suggested_action)
    msg = f"Recorded request: {result['pattern']} ({result['frequency']}x)"
    if result["auto_eligible"]:
        msg += " — AUTO-ELIGIBLE: consider performing this proactively"
    return msg


@mcp.tool()
def get_user_profile(category: str | None = None) -> str:
    """Get the user's profile — all observations and recurrent request patterns.

    Args:
        category: Optional filter (emotion, habit, problem, victory, preference, etc.)
    """
    up = _get_user_profile()
    if up is None:
        return "User profile is not enabled. Enable with: update_settings(user_profile_enabled=True)"

    observations = up.get_all_observations(category=category, min_confidence=0.2)
    requests = up.get_recurrent_requests(min_frequency=1)

    lines = ["User Profile"]
    if observations:
        current_cat = ""
        for obs in observations:
            if obs.category != current_cat:
                current_cat = obs.category
                lines.append(f"\n  [{current_cat}]")
            conf_bar = "●" * int(obs.confidence * 5) + "○" * (5 - int(obs.confidence * 5))
            lines.append(f"    {conf_bar} {obs.content} ({obs.frequency}x)")
    else:
        lines.append("  No observations yet.")

    if requests:
        lines.append("\n  [recurrent requests]")
        for r in requests:
            auto = " ★" if r["auto_eligible"] else ""
            lines.append(f"    {r['pattern']} ({r['frequency']}x){auto}")
            if r["suggested_action"]:
                lines.append(f"      → auto: {r['suggested_action']}")

    stats = up.stats()
    lines.append(f"\n  Total: {stats['total_observations']} observations, "
                 f"{stats['request_patterns']} patterns")

    return "\n".join(lines)


@mcp.tool()
def delete_user_observation(
    observation_id: str | None = None,
    category: str | None = None,
    delete_all: bool = False,
) -> str:
    """Delete user profile observations. The user controls their own data.

    Args:
        observation_id: Delete a specific observation by ID
        category: Delete all observations in a category
        delete_all: Delete entire profile (requires explicit True)
    """
    up = _get_user_profile()
    if up is None:
        return "User profile is not enabled."

    if delete_all:
        count = up.delete_all()
        return f"Deleted entire profile ({count} observations)."
    elif category:
        count = up.delete_category(category)
        return f"Deleted {count} observations in category '{category}'."
    elif observation_id:
        if up.delete_observation(observation_id):
            return f"Deleted observation {observation_id}."
        return f"Observation {observation_id} not found."
    else:
        return "Specify observation_id, category, or delete_all=True."


# ------------------------------------------------------------------
# Think Tank Tools
# ------------------------------------------------------------------

@mcp.tool()
def start_think_tank(
    topic: str,
    template: str = "brainstorm",
    participants: list[str] | None = None,
) -> str:
    """Start a Think Tank session — multi-agent brainstorming with AI executives.

    Assembles a panel of AI executives (CEO, CTO, Creative Director, etc.) who each
    respond from their unique expertise. Use this for strategic decisions, product
    innovation, architecture reviews, risk assessment, or open brainstorming.

    Templates: strategic_planning, product_innovation, architecture_review,
    risk_assessment, brainstorm (default).

    Participants: CEO_Strategic, CTO_Innovation, Creative_Director, Research_Lead,
    Product_Strategist, Finance_Analyst. Template selects defaults if not specified.

    Args:
        topic: What to discuss
        template: Session type (default: brainstorm)
        participants: Override default participants for the template
    """
    tt = _get_think_tank()
    meeting = tt.start_meeting(topic, template=template, participants=participants)
    tmpl = TEMPLATES.get(template, TEMPLATES["brainstorm"])

    lines = [
        f"Think Tank session started: {meeting.meeting_id}",
        f"  Topic: {topic}",
        f"  Template: {tmpl['name']}",
        f"  Participants: {', '.join(meeting.participants)}",
        f"  Focus: {tmpl['focus']}",
        "",
        "Use discuss_think_tank() to send messages and get responses from each executive.",
        "Use conclude_think_tank() when done to save decisions and generate effectiveness report.",
    ]
    return "\n".join(lines)


@mcp.tool()
async def discuss_think_tank(meeting_id: str, message: str) -> str:
    """Send a message to the Think Tank and get responses from all executives.

    Each participant responds from their unique expertise perspective.
    Requires OpenRouter API key (same as ensemble mode).

    Args:
        meeting_id: The meeting ID from start_think_tank()
        message: Your message or question for the panel
    """
    tt = _get_think_tank()
    settings = _load_settings()
    ev = settings.get("external_validation", {})
    api_key = ev.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
    model = ev.get("model", "google/gemini-2.5-flash")

    if not api_key:
        return "OpenRouter API key required. Set via /ec:configure or OPENROUTER_API_KEY env var."

    responses = await tt.run_round(meeting_id, message, api_key, model)
    if not responses:
        return f"Meeting {meeting_id} not found or no responses generated."

    lines = [f"Round responses for: {message[:80]}...\n"]
    for resp in responses:
        exec_info = EXECUTIVES.get(resp["sender"], {})
        role = exec_info.get("role", "Expert")
        lines.append(f"[{resp['sender']}] ({role})")
        lines.append(resp["content"])
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def conclude_think_tank(
    meeting_id: str,
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    """Conclude a Think Tank session — save decisions and generate effectiveness report.

    Args:
        meeting_id: The meeting ID
        decisions: Key decisions made during the session
        next_steps: Action items from the session
    """
    tt = _get_think_tank()
    try:
        meeting = tt.conclude_meeting(meeting_id, decisions=decisions, next_steps=next_steps)
    except ValueError as exc:
        return str(exc)

    eff = meeting.effectiveness
    lines = [
        f"Think Tank concluded: {meeting.meeting_id}",
        f"  Topic: {meeting.topic}",
        f"  Rounds: {meeting.rounds_completed}",
        f"  Messages: {len(meeting.messages)}",
        "",
        "Effectiveness:",
        f"  Engagement: {eff.get('engagement', 0)}",
        f"  Depth: {eff.get('depth', 0)}",
        f"  Productivity: {eff.get('productivity', 0)}",
        f"  Overall: {eff.get('overall', 0)} — {eff.get('rating', 'N/A')}",
    ]
    if meeting.decisions:
        lines.append("\nDecisions:")
        for d in meeting.decisions:
            lines.append(f"  - {d}")
    return "\n".join(lines)


@mcp.tool()
def list_think_tank_sessions(limit: int = 10) -> str:
    """List recent and active Think Tank sessions.

    Args:
        limit: Max past sessions to show
    """
    tt = _get_think_tank()
    active = tt.get_active_meetings()
    past = tt.list_meetings(limit=limit)

    lines = []
    if active:
        lines.append(f"Active sessions ({len(active)}):")
        for mid in active:
            lines.append(f"  - {mid}")

    if past:
        lines.append(f"\nPast sessions ({len(past)}):")
        for m in past:
            eff = m.get("effectiveness", {})
            lines.append(f"  {m['meeting_id']}: {m['topic']} — {eff.get('rating', '?')}")

    if not lines:
        lines.append("No think tank sessions yet. Start one with start_think_tank().")

    # Show available templates
    lines.append("\nAvailable templates:")
    for tid, t in TEMPLATES.items():
        lines.append(f"  {tid}: {t['name']} ({', '.join(t['participants'][:3])}...)")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Merit System Tools
# ------------------------------------------------------------------

@mcp.tool()
def award_merit(
    category: str,
    reason: str,
    points: int | None = None,
) -> str:
    """Award merit points for good work.

    Call this silently when:
    - A task is completed successfully (task_completed, +10)
    - The user gives positive feedback (positive_feedback, +5)
    - You proactively helped the user (proactive_action, +3)
    - You caught a bug before it shipped (bug_caught, +8)
    - You wrote tests (test_written, +2)
    - Code review passed clean (clean_review, +4)
    - You created a useful module (module_created, +6)
    - You advanced a user objective (objective_advanced, +7)
    - Outstanding work (excellent_work, +15)

    Also call for deductions:
    - Task failed/reverted (task_failed, -5)
    - User frustrated by your action (user_frustrated, -3)
    - Scope creep (scope_creep, -2)

    Args:
        category: Merit category (see above)
        reason: Why points were awarded (concise)
        points: Override default points (optional)
    """
    ledger = _get_merit_ledger()
    project = os.path.basename(_detect_project_root())
    entry = ledger.award(category, reason, points=points, project=project)
    rank = ledger.get_rank()
    return (f"Merit: {entry.points:+d} ({entry.category}) — {entry.reason}\n"
            f"Total: {rank['total_points']} pts | Rank: {rank['rank']}\n"
            f"Next: {rank['next_rank']} ({rank['points_to_next']} pts away)")


@mcp.tool()
def get_merits(show_log: bool = False, limit: int = 10) -> str:
    """Get current merit status — rank, points, stats, and optionally recent log.

    Args:
        show_log: Show recent merit events (default: False)
        limit: Number of log entries to show (default: 10)
    """
    ledger = _get_merit_ledger()
    stats = ledger.get_stats()

    lines = [
        f"Merit Status: {stats['rank']}",
        f"  Total points: {stats['total_points']}",
        f"  Next rank: {stats['next_rank']} ({stats['points_to_next']} pts away)",
        f"  Positive streak: {stats['positive_streak']}",
        f"  Total events: {stats['total_events']}",
    ]

    if stats["by_category"]:
        lines.append("\n  By category:")
        for cat, info in sorted(stats["by_category"].items(),
                                 key=lambda x: x[1]["points"], reverse=True):
            lines.append(f"    {cat}: {info['points']:+d} ({info['count']}x)")

    if stats["by_project"]:
        lines.append("\n  By project:")
        for proj, info in stats["by_project"].items():
            lines.append(f"    {proj}: {info['points']:+d} ({info['count']}x)")

    if show_log:
        log = ledger.get_log(limit=limit)
        if log:
            lines.append(f"\n  Recent ({len(log)}):")
            for e in log:
                ts = time.strftime("%m-%d %H:%M", time.localtime(e.timestamp))
                lines.append(f"    [{ts}] {e.points:+d} {e.category}: {e.reason}")

    # Show rank progression
    lines.append("\n  Ranks:")
    for threshold, title in RANKS:
        marker = " <<" if title == stats["rank"] else ""
        lines.append(f"    {threshold:>5} pts — {title}{marker}")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Module System Tools
# ------------------------------------------------------------------

@mcp.tool()
def create_module(
    name: str,
    description: str,
    code: str,
    module_type: str = "tool",
    scope: str = "project",
    triggers: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create a new elephant module — extend elephant-coder with custom functionality.

    Write Python code that defines a run(args: dict) -> str function.
    The module will be saved and can be executed via run_module().

    Module types: tool, analyzer, workflow, checker, generator, mcp_server.

    For mcp_server type, use create_mcp_module() instead — it creates a full
    MCP server with its own tools, skills, and hooks.

    Args:
        name: Module name (lowercase, underscores)
        description: What this module does
        code: Python code (must define run(args: dict) -> str, or body will be wrapped)
        module_type: Type of module (tool, analyzer, workflow, checker, generator)
        scope: "project" (this project only) or "global" (all projects)
        triggers: Events that trigger this module (e.g. ["PostToolUse:Edit"])
        tags: Classification tags
    """
    ms = _get_module_system()
    try:
        mod = ms.create_module(name, description, code,
                               module_type=module_type, scope=scope,
                               triggers=triggers, tags=tags)
        return (f"Created module '{mod.name}' ({mod.module_type}, {mod.scope})\n"
                f"Path: {mod.path}\n"
                f"Run with: run_module('{mod.name}')")
    except Exception as exc:
        return f"Failed to create module: {exc}"


@mcp.tool()
def create_mcp_module(
    name: str,
    description: str,
    tools_code: str,
    skills: list[dict] | None = None,
    hooks: list[dict] | None = None,
    scope: str = "project",
    tags: list[str] | None = None,
) -> str:
    """Create a full MCP sub-server module with its own tools, skills, and hooks.

    This is the most powerful module type — creates an entire MCP server within
    elephant-coder. The server can define @mcp.tool() functions, slash command
    skills, and event hooks.

    The tools_code should define @mcp.tool() decorated functions. The 'mcp' object
    (FastMCP instance) is pre-defined — just write the tool functions.

    Args:
        name: Server name (becomes ec-<name> in MCP registry)
        description: What this server does
        tools_code: Python code with @mcp.tool() functions (mcp object is pre-defined)
        skills: List of {"name": str, "description": str, "content": str} for slash commands
        hooks: List of {"event": str, "name": str, "description": str, "code": str, "matcher": str}
        scope: "project" or "global"
        tags: Classification tags
    """
    ms = _get_module_system()
    try:
        mod = ms.create_mcp_module(name, description, tools_code,
                                    skills=skills, hooks=hooks,
                                    scope=scope, tags=tags)
        lines = [
            f"Created MCP module '{mod.name}'",
            f"  Path: {mod.path}",
            f"  Server: ec-{mod.name}",
        ]
        if skills:
            lines.append(f"  Skills: {len(skills)}")
        if hooks:
            lines.append(f"  Hooks: {len(hooks)}")
        lines.append(f"\nTo register: add the .mcp.json config to Claude Code settings")
        lines.append(f"MCP config: {mod.path}/.mcp.json")
        return "\n".join(lines)
    except Exception as exc:
        return f"Failed to create MCP module: {exc}"


@mcp.tool()
def list_modules(
    scope: str | None = None,
    module_type: str | None = None,
) -> str:
    """List all installed elephant modules.

    Args:
        scope: Filter by scope ("global" or "project"), None for all
        module_type: Filter by type ("tool", "analyzer", "mcp_server", etc.), None for all
    """
    ms = _get_module_system()
    modules = ms.list_modules(scope=scope, module_type=module_type)

    if not modules:
        lines = ["No modules installed."]
        # Check for suggestions
        suggestions = ms.suggest_modules()
        if suggestions:
            lines.append("\nSuggested modules (based on user patterns):")
            for s in suggestions:
                lines.append(f"  - {s['name']}: {s['reason']}")
        return "\n".join(lines)

    lines = [f"Installed modules ({len(modules)}):"]
    for m in modules:
        status = "●" if m.active else "○"
        lines.append(f"  {status} {m.name} ({m.module_type}, {m.scope}) — {m.description}")
        if m.use_count:
            lines.append(f"      used {m.use_count}x")
    return "\n".join(lines)


@mcp.tool()
def run_module(name: str, args: str | None = None) -> str:
    """Execute an elephant module.

    Runs the module's run() function in an isolated subprocess.
    Pass arguments as a JSON string.

    Args:
        name: Module name to execute
        args: JSON string of arguments (e.g. '{"file": "src/main.py"}')
    """
    ms = _get_module_system()
    parsed_args = {}
    if args:
        try:
            parsed_args = json.loads(args)
        except json.JSONDecodeError:
            return f"Invalid args JSON: {args}"
    return ms.run_module(name, parsed_args)


@mcp.tool()
def update_module(
    name: str,
    code: str | None = None,
    description: str | None = None,
    active: bool | None = None,
) -> str:
    """Update an existing elephant module.

    Args:
        name: Module name to update
        code: New Python code (replaces existing)
        description: New description
        active: True to activate, False to deactivate
    """
    ms = _get_module_system()
    return ms.update_module(name, code=code, description=description, active=active)


@mcp.tool()
def delete_module(name: str) -> str:
    """Delete an elephant module and all its files.

    Args:
        name: Module name to delete
    """
    ms = _get_module_system()
    return ms.delete_module(name)


@mcp.tool()
def get_module_code(name: str) -> str:
    """Read a module's source code for review or modification.

    Args:
        name: Module name to read
    """
    ms = _get_module_system()
    return ms.get_module_code(name)


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
    conn = store._get_sqlite()
    rows = conn.execute(
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
    parser.add_argument("--redis-url", default=None, help="Redis URL (default: redis://localhost:6379)")
    args = parser.parse_args()

    if args.redis_url:
        _redis_url = args.redis_url

    import atexit

    def _shutdown():
        """Flush all stores to SQLite on exit."""
        logger.info("Shutting down — flushing stores to SQLite...")
        for store in _stores.values():
            try:
                store.close()
            except Exception as exc:
                logger.error("Failed to flush store: %s", exc)
        for vs in _vector_stores.values():
            try:
                vs.flush()
            except Exception:
                pass
        if _merit_ledger:
            try:
                _merit_ledger.close()
            except Exception:
                pass
        logger.info("Shutdown complete.")

    atexit.register(_shutdown)

    mcp.run(transport="stdio")
