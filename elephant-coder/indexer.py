"""
Multi-language code indexer for elephant-coder.

Compresses source files into MemoryEntry capsules using AST/regex parsing.
This is the "Capsule Encoding" step — analogous to CapsuleProject (nn/capsule.py)
which compresses 384D embeddings into 32D capsules.

The keyword extraction is the "Dentate Gyrus" step — producing a sparse set of
discriminative tokens for efficient FTS5 retrieval (pattern separation).

Supported languages:
- Python (.py) — full AST parsing
- TypeScript/JavaScript (.ts/.js/.tsx/.jsx) — regex extraction
- C/C++ (.c/.cpp/.cc/.cxx/.h/.hpp/.hxx) — regex extraction
- GLSL shaders (.glsl/.vert/.frag/.comp) — regex extraction
- Markdown (.md) — heading/section extraction
- PDF (.pdf) — text extraction via pypdf
- TOML (.toml) — key/table extraction
- JSON (.json) — key/structure extraction
- YAML (.yaml/.yml) — key/structure extraction
- CMake (CMakeLists.txt/.cmake) — target/variable extraction
"""

import ast
import json as json_lib
import logging
import os
import re
import sys
from pathlib import Path

from memory_store import MemoryEntry, make_memory_id

logger = logging.getLogger("elephant-coder.indexer")

# Max chars for docstring excerpts
_MAX_DOC = 200
# Max methods to list in a class summary
_MAX_METHODS = 40


def _count_lines(file_path: str) -> int:
    """Count lines in a file efficiently."""
    try:
        with open(file_path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def index_file(file_path: str) -> list[MemoryEntry]:
    """Parse a source file and produce MemoryEntry objects for each symbol.

    Every module-level entry includes line_count so callers can decide
    whether to use smart_read (500+ lines) or regular Read before opening.
    """
    path = Path(file_path)
    if not path.exists():
        return []

    suffix = path.suffix.lower()
    name = path.name.lower()

    entries: list[MemoryEntry] = []
    if suffix == ".py":
        entries = _index_py_file(file_path)
    elif suffix in (".ts", ".js", ".tsx", ".jsx"):
        entries = _index_ts_file(file_path)
    elif suffix in (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"):
        entries = _index_cpp_file(file_path)
    elif suffix in (".glsl", ".vert", ".frag", ".comp", ".geom", ".tesc", ".tese"):
        entries = _index_glsl_file(file_path)
    elif suffix == ".md":
        entries = _index_md_file(file_path)
    elif suffix == ".pdf":
        entries = _index_pdf_file(file_path)
    elif suffix == ".toml":
        entries = _index_toml_file(file_path)
    elif suffix == ".json":
        entries = _index_json_file(file_path)
    elif suffix in (".yaml", ".yml"):
        entries = _index_yaml_file(file_path)
    elif suffix == ".cmake" or name == "cmakelists.txt":
        entries = _index_cmake_file(file_path)

    # Stamp line_count on all module-level entries
    if entries:
        lc = _count_lines(file_path)
        for e in entries:
            if e.kind == "module":
                e.line_count = lc

    return entries


def _index_py_file(file_path: str) -> list[MemoryEntry]:
    """Parse a Python file and produce MemoryEntry objects for each symbol."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        logger.debug("Failed to parse %s: %s", file_path, exc)
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []

    # Module-level entry
    entries.append(_module_entry(file_path, tree, source, file_mtime))

    # Top-level classes and functions
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            entries.append(_class_entry(file_path, node, source, file_mtime))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entries.append(_function_entry(file_path, node, source, file_mtime))

    return entries


# ------------------------------------------------------------------
# TypeScript/JavaScript indexing via regex
# ------------------------------------------------------------------

_TS_FUNCTION_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
_TS_ARROW_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*(?::\s*\w+)?\s*=>",
    re.MULTILINE,
)
_TS_CLASS_RE = re.compile(
    r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?\s*\{",
    re.MULTILINE,
)
_TS_EXPORT_RE = re.compile(
    r"export\s+(?:default\s+)?(?:const|let|var|type|interface|enum)\s+(\w+)",
    re.MULTILINE,
)


def _index_ts_file(file_path: str) -> list[MemoryEntry]:
    """Index a TypeScript/JavaScript file via regex extraction."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    functions = []
    classes = []
    exports = []

    # Extract functions
    for m in _TS_FUNCTION_RE.finditer(source):
        name = m.group(1)
        params = m.group(2).strip()
        functions.append(name)
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=f"function {name}({params})",
            keywords=_extract_keywords_from_strings([name, params]),
            file_mtime=file_mtime,
        ))

    # Extract arrow functions
    for m in _TS_ARROW_RE.finditer(source):
        name = m.group(1)
        if name not in functions:
            functions.append(name)
            entries.append(MemoryEntry(
                memory_id=make_memory_id(file_path, name, "function"),
                file_path=file_path,
                symbol_name=name,
                kind="function",
                summary=f"const {name} = (...) =>",
                keywords=_extract_keywords_from_strings([name]),
                file_mtime=file_mtime,
            ))

    # Extract classes
    for m in _TS_CLASS_RE.finditer(source):
        name = m.group(1)
        extends = m.group(2) or ""
        classes.append(name)
        summary = f"class {name}"
        if extends:
            summary += f" extends {extends}"
        deps = [extends] if extends else []
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=summary,
            keywords=_extract_keywords_from_strings([name, extends]),
            dependencies=deps,
            file_mtime=file_mtime,
        ))

    # Extract other exports
    for m in _TS_EXPORT_RE.finditer(source):
        name = m.group(1)
        if name not in functions and name not in classes:
            exports.append(name)

    # Module entry
    top_symbols = [f"function {f}" for f in functions] + [f"class {c}" for c in classes] + exports
    summary_parts = []
    if top_symbols:
        summary_parts.append("Defines: " + ", ".join(top_symbols))

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts) if summary_parts else f"Module {module_name}",
        keywords=_extract_keywords_from_strings([module_name] + functions + classes + exports),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# C/C++ indexing via regex
# ------------------------------------------------------------------

# Match: #include <...> or #include "..."
_CPP_INCLUDE_RE = re.compile(
    r'^\s*#include\s+[<"]([^>"]+)[>"]', re.MULTILINE
)

# Match: #define NAME (value or macro)
_CPP_DEFINE_RE = re.compile(
    r'^\s*#define\s+(\w+)(?:\(([^)]*)\))?\s*(.*?)$', re.MULTILINE
)

# Match: namespace name {
_CPP_NAMESPACE_RE = re.compile(
    r'(?:^|\n)\s*namespace\s+(\w+)\s*\{', re.MULTILINE
)

# Match: enum [class] Name [: type] {
_CPP_ENUM_RE = re.compile(
    r'(?:^|\n)\s*enum\s+(?:class\s+)?(\w+)(?:\s*:\s*\w+)?\s*\{([^}]*)\}',
    re.MULTILINE | re.DOTALL,
)

# Match: typedef ... Name;
_CPP_TYPEDEF_RE = re.compile(
    r'(?:^|\n)\s*typedef\s+(.+?)\s+(\w+)\s*;', re.MULTILINE
)

# Match: using Name = ...;
_CPP_USING_RE = re.compile(
    r'(?:^|\n)\s*using\s+(\w+)\s*=\s*(.+?)\s*;', re.MULTILINE
)

# Match: class/struct Name [: bases] { (including template prefix)
_CPP_CLASS_RE = re.compile(
    r'(?:template\s*<[^>]*>\s*)?(?:class|struct)\s+(?:\w+\s+)?(\w+)'
    r'(?:\s*(?:final\s*)?:\s*((?:(?:public|protected|private)\s+)?[\w:<>, ]+(?:\s*,\s*(?:(?:public|protected|private)\s+)?[\w:<>, ]+)*))?'
    r'\s*\{',
    re.MULTILINE,
)

# Match top-level and member function definitions/declarations
# Handles: ReturnType [Class::]FuncName(params) [const] [override] [= 0] [{ ... }|;]
_CPP_FUNC_RE = re.compile(
    r'(?:^|\n)[ \t]*'                                       # line start + indent
    r'(?:(?:template\s*<[^>]*>\s*)?'                        # optional template
    r'(?:(?:static|virtual|inline|explicit|constexpr|friend|extern)\s+)*'  # qualifiers
    r'(?:const\s+)?'                                        # const return
    r'([\w:<>&*\s]+?)\s+'                                   # return type (group 1)
    r'(~?\w+)\s*'                                           # function name (group 2)
    r'\(([^)]*)\)'                                          # params (group 3)
    r'(?:\s*(?:const|noexcept|override|final|=\s*0|=\s*default|=\s*delete))*'  # suffixes
    r'\s*(?:\{|;))',                                         # body or declaration
    re.MULTILINE,
)

# Match method declarations inside class bodies (simpler pattern for headers)
_CPP_METHOD_DECL_RE = re.compile(
    r'^\s*(?:(?:static|virtual|inline|explicit|constexpr|friend)\s+)*'
    r'(?:const\s+)?'
    r'([\w:<>&*\s]+?)\s+'
    r'(~?\w+)\s*'
    r'\(([^)]*)\)'
    r'(?:\s*(?:const|noexcept|override|final|=\s*0|=\s*default|=\s*delete))*'
    r'\s*(?:\{|;)',
    re.MULTILINE,
)


def _strip_cpp_comments(source: str) -> str:
    """Remove C/C++ comments to avoid false regex matches."""
    # Remove // line comments
    source = re.sub(r'//[^\n]*', '', source)
    # Remove /* block comments */
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    return source


def _extract_class_body(source: str, class_match: re.Match) -> str | None:
    """Extract the body of a class/struct by brace matching from a regex match."""
    start = class_match.end() - 1  # position of opening {
    if start >= len(source) or source[start] != '{':
        return None
    depth = 1
    i = start + 1
    while i < len(source) and depth > 0:
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
        i += 1
    if depth == 0:
        return source[start + 1 : i - 1]
    return None


def _index_cpp_file(file_path: str) -> list[MemoryEntry]:
    """Index a C/C++ file via regex extraction of classes, functions, etc."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    clean = _strip_cpp_comments(source)
    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    includes = []
    namespaces = []
    classes = []
    functions = []
    enums = []
    defines = []

    # --- Includes (dependencies) ---
    for m in _CPP_INCLUDE_RE.finditer(clean):
        includes.append(m.group(1))

    # --- Namespaces ---
    for m in _CPP_NAMESPACE_RE.finditer(clean):
        namespaces.append(m.group(1))

    # --- Enums ---
    for m in _CPP_ENUM_RE.finditer(clean):
        name = m.group(1)
        body = m.group(2).strip()
        # Extract enum values
        values = [v.strip().split('=')[0].strip()
                  for v in body.split(',') if v.strip()]
        values = [v for v in values if v and re.match(r'^\w+$', v)]
        enums.append(name)
        summary = f"enum {name}"
        if values:
            shown = values[:10]
            summary += " { " + ", ".join(shown)
            if len(values) > 10:
                summary += f", ... +{len(values) - 10}"
            summary += " }"
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=summary,
            keywords=_extract_keywords_from_strings([name] + values[:10]),
            file_mtime=file_mtime,
        ))

    # --- Classes / Structs ---
    for m in _CPP_CLASS_RE.finditer(clean):
        name = m.group(1)
        bases_str = m.group(2) or ""
        bases = [b.strip().split()[-1] for b in bases_str.split(',') if b.strip()] if bases_str else []
        classes.append(name)

        # Extract methods from class body
        body = _extract_class_body(clean, m)
        methods = []
        attrs = []
        if body:
            for mm in _CPP_METHOD_DECL_RE.finditer(body):
                ret = mm.group(1).strip()
                mname = mm.group(2)
                params = mm.group(3).strip()
                # Skip if return type looks like a control keyword
                if ret in ('if', 'else', 'for', 'while', 'switch', 'return', 'case'):
                    continue
                sig = f"{ret} {mname}({params})"
                methods.append(sig)

        summary_parts = []
        head = f"class {name}" if 'struct' not in clean[max(0, m.start()-10):m.start()+10] else f"struct {name}"
        if bases:
            head += f" : {', '.join(bases)}"
        summary_parts.append(head)
        if methods:
            shown = methods[:_MAX_METHODS]
            summary_parts.append("Methods:\n  " + "\n  ".join(shown))
            if len(methods) > _MAX_METHODS:
                summary_parts.append(f"  ... +{len(methods) - _MAX_METHODS} more")

        method_names = [sig.split('(')[0].split()[-1] for sig in methods]
        keywords = _extract_keywords_from_strings(
            [name] + bases + method_names
        )

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary="\n".join(summary_parts),
            keywords=keywords,
            dependencies=bases,
            file_mtime=file_mtime,
        ))

    # --- Free functions (not inside class bodies) ---
    class_names_set = set(classes)
    for m in _CPP_FUNC_RE.finditer(clean):
        ret = m.group(1).strip()
        name = m.group(2)
        params = m.group(3).strip()
        # Skip constructors/destructors already captured in classes
        if name in class_names_set or name.lstrip('~') in class_names_set:
            continue
        # Skip if return type looks like a control keyword
        if ret in ('if', 'else', 'for', 'while', 'switch', 'return', 'case', 'namespace', 'class', 'struct', 'enum', 'using', 'typedef'):
            continue
        # Handle Class::Method — extract as class method
        if '::' in name:
            parts = name.split('::')
            name = parts[-1]
            qualifier = '::'.join(parts[:-1])
            sig = f"{ret} {qualifier}::{name}({params})"
        else:
            sig = f"{ret} {name}({params})"
        functions.append(name)

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=sig,
            keywords=_extract_keywords_from_strings([name, ret, params]),
            file_mtime=file_mtime,
        ))

    # --- #define constants/macros ---
    for m in _CPP_DEFINE_RE.finditer(clean):
        name = m.group(1)
        macro_params = m.group(2)
        value = m.group(3).strip()
        # Skip include guards and common non-informative defines
        if name.startswith('_') and name.endswith('_H'):
            continue
        if name.startswith('_') and name.endswith('_HPP'):
            continue
        defines.append(name)
        if macro_params is not None:
            summary = f"#define {name}({macro_params})"
        elif value and len(value) < 80:
            summary = f"#define {name} {value}"
        else:
            summary = f"#define {name}"
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=summary,
            keywords=_extract_keywords_from_strings([name]),
            file_mtime=file_mtime,
        ))

    # --- Typedefs ---
    for m in _CPP_TYPEDEF_RE.finditer(clean):
        typedef_body = m.group(1).strip()
        name = m.group(2)
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=f"typedef {typedef_body} {name}",
            keywords=_extract_keywords_from_strings([name, typedef_body]),
            file_mtime=file_mtime,
        ))

    # --- Using aliases ---
    for m in _CPP_USING_RE.finditer(clean):
        name = m.group(1)
        target = m.group(2).strip()
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=f"using {name} = {target}",
            keywords=_extract_keywords_from_strings([name, target]),
            file_mtime=file_mtime,
        ))

    # --- Module entry ---
    top_symbols = (
        [f"class {c}" for c in classes]
        + [f"enum {e}" for e in enums]
        + [f"function {f}" for f in functions[:20]]
    )
    summary_parts = []
    if namespaces:
        summary_parts.append("Namespaces: " + ", ".join(sorted(set(namespaces))))
    if top_symbols:
        summary_parts.append("Defines: " + ", ".join(top_symbols))
    if includes:
        summary_parts.append("Includes: " + ", ".join(includes[:15]))
        if len(includes) > 15:
            summary_parts.append(f"  ... +{len(includes) - 15} more")

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts) if summary_parts else f"C/C++ module {module_name}",
        keywords=_extract_keywords_from_strings(
            [module_name] + classes + functions + enums + namespaces
        ),
        dependencies=includes,
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# Python entry builders
# ------------------------------------------------------------------


def _module_entry(file_path: str, tree: ast.Module, source: str, file_mtime: float) -> MemoryEntry:
    """Build a module-level summary."""
    doc = _get_docstring(tree)
    imports = _extract_imports(tree)
    all_names = _extract_all(tree)
    constants = _extract_constants(tree)
    top_symbols = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            top_symbols.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_symbols.append(f"def {node.name}")

    summary_parts = []
    if doc:
        summary_parts.append(doc[:_MAX_DOC])
    if all_names:
        summary_parts.append(f"__all__ = {all_names}")
    if top_symbols:
        summary_parts.append("Defines: " + ", ".join(top_symbols))
    if constants:
        summary_parts.append("Constants: " + ", ".join(constants[:10]))

    module_name = Path(file_path).stem
    keywords = _extract_keywords_from_strings(
        [module_name, doc or ""] + top_symbols + imports + constants
    )

    return MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts) if summary_parts else f"Module {module_name}",
        keywords=keywords,
        dependencies=imports,
        file_mtime=file_mtime,
    )


def _class_entry(file_path: str, node: ast.ClassDef, source: str, file_mtime: float) -> MemoryEntry:
    """Build a class summary: name, bases, inheritance chain, docstring, method signatures."""
    doc = _get_docstring(node)
    bases = [_unparse_safe(b) for b in node.bases]

    # Extract full inheritance chain info from bases
    inheritance = bases[:]

    methods = []
    attrs = []
    properties = []
    class_vars = []
    decorators = [_unparse_safe(d) for d in node.decorator_list]

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _function_signature(item)
            # Check for property decorators
            for d in item.decorator_list:
                dname = _unparse_safe(d)
                if "property" in dname:
                    properties.append(item.name)
                    break
            methods.append(sig)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            ann = _unparse_safe(item.annotation) if item.annotation else "?"
            attrs.append(f"{item.target.id}: {ann}")
        elif isinstance(item, ast.Assign):
            # Class variables
            for target in item.targets:
                if isinstance(target, ast.Name):
                    class_vars.append(target.id)

    summary_parts = []
    head = f"class {node.name}"
    if bases:
        head += f"({', '.join(bases)})"
    if decorators:
        for dec in decorators:
            summary_parts.append(f"@{dec}")
    summary_parts.append(head)
    if doc:
        summary_parts.append(doc[:_MAX_DOC])
    if attrs:
        summary_parts.append("Attrs: " + ", ".join(attrs[:10]))
    if class_vars:
        summary_parts.append("ClassVars: " + ", ".join(class_vars[:10]))
    if properties:
        summary_parts.append("Properties: " + ", ".join(properties[:10]))
    if methods:
        shown = methods[:_MAX_METHODS]
        summary_parts.append("Methods:\n  " + "\n  ".join(shown))
        if len(methods) > _MAX_METHODS:
            summary_parts.append(f"  ... +{len(methods) - _MAX_METHODS} more")

    # Richer keywords: include method names, parameter names, decorator names, type annotations
    method_names = [m.split("(")[0].replace("def ", "").replace("async def ", "") for m in methods]
    keywords = _extract_keywords_from_strings(
        [node.name, doc or ""]
        + inheritance
        + method_names
        + decorators
        + class_vars
        + [a.split(":")[0].strip() for a in attrs]
    )
    deps = bases + _extract_calls(node)

    return MemoryEntry(
        memory_id=make_memory_id(file_path, node.name, "class"),
        file_path=file_path,
        symbol_name=node.name,
        kind="class",
        summary="\n".join(summary_parts),
        keywords=keywords,
        dependencies=deps,
        file_mtime=file_mtime,
    )


def _function_entry(
    file_path: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    file_mtime: float,
) -> MemoryEntry:
    """Build a function summary: signature, docstring, return type, calls."""
    doc = _get_docstring(node)
    sig = _function_signature(node)
    ret = _unparse_safe(node.returns) if node.returns else None
    calls = _extract_calls(node)
    decorators = [_unparse_safe(d) for d in node.decorator_list]

    # Extract parameter names and type annotations for keywords
    param_names = [arg.arg for arg in node.args.args if arg.arg != "self"]
    param_types = []
    for arg in node.args.args:
        if arg.annotation:
            param_types.append(_unparse_safe(arg.annotation))

    summary_parts = []
    if decorators:
        for dec in decorators:
            summary_parts.append(f"@{dec}")
    summary_parts.append(sig)
    if doc:
        summary_parts.append(doc[:_MAX_DOC])
    if ret:
        summary_parts.append(f"Returns: {ret}")
    if calls:
        summary_parts.append(f"Calls: {', '.join(calls[:15])}")

    keywords = _extract_keywords_from_strings(
        [node.name, doc or ""]
        + calls
        + param_names
        + param_types
        + decorators
        + ([ret] if ret else [])
    )

    return MemoryEntry(
        memory_id=make_memory_id(file_path, node.name, "function"),
        file_path=file_path,
        symbol_name=node.name,
        kind="function",
        summary="\n".join(summary_parts),
        keywords=keywords,
        dependencies=calls,
        file_mtime=file_mtime,
    )


# ------------------------------------------------------------------
# AST helpers
# ------------------------------------------------------------------


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a module, class, or function node."""
    try:
        doc = ast.get_docstring(node)
        return doc.strip() if doc else None
    except Exception:
        return None


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Produce a compact signature string like 'def foo(x: int, y: str) -> bool'."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    params = []
    for arg in node.args.args:
        ann = f": {_unparse_safe(arg.annotation)}" if arg.annotation else ""
        params.append(f"{arg.arg}{ann}")
    if node.args.vararg:
        params.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        params.append(f"**{node.args.kwarg.arg}")

    ret = f" -> {_unparse_safe(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({', '.join(params)}){ret}"


def _extract_imports(tree: ast.Module) -> list[str]:
    """Extract import names from a module AST."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}")
    return sorted(set(imports))


def _extract_all(tree: ast.Module) -> list[str] | None:
    """Extract __all__ list if defined."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return [_unparse_safe(elt) for elt in node.value.elts]
    return None


def _extract_constants(tree: ast.Module) -> list[str]:
    """Extract module-level constant assignments (UPPER_CASE names)."""
    constants = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) >= 2:
                    val = _unparse_safe(node.value)
                    if len(val) < 60:
                        constants.append(f"{target.id} = {val}")
                    else:
                        constants.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper() and len(node.target.id) >= 2:
                constants.append(node.target.id)
    return constants


def _extract_calls(node: ast.AST) -> list[str]:
    """Extract function/method call names from an AST subtree."""
    calls = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.add(child.func.attr)
    return sorted(calls)


def _unparse_safe(node: ast.AST | None) -> str:
    """Safely unparse an AST node to string."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def _extract_keywords_from_strings(strings: list[str]) -> list[str]:
    """Extract discriminative keywords from a list of strings.

    Splits camelCase and snake_case identifiers, lowercases, deduplicates.
    This is the "DG sparse expansion" — producing a sparse set of tokens
    that disambiguate this entry from others.
    """
    tokens: set[str] = set()
    for s in strings:
        if not s:
            continue
        # Split on non-alphanumeric
        parts = re.split(r"[^a-zA-Z0-9]+", s)
        for part in parts:
            if not part or len(part) < 2:
                continue
            # Split camelCase
            sub = re.sub(r"([a-z])([A-Z])", r"\1 \2", part).split()
            for token in sub:
                low = token.lower()
                if len(low) >= 2 and low not in _STOP_WORDS:
                    tokens.add(low)
    return sorted(tokens)


# ------------------------------------------------------------------
# GLSL shader indexing via regex
# ------------------------------------------------------------------

# layout(local_size_x = N, ...) in;
_GLSL_LAYOUT_RE = re.compile(
    r'layout\s*\(([^)]+)\)\s*(?:in|out|uniform|buffer|std430|std140)\b',
    re.MULTILINE,
)
# layout(...) uniform/buffer BlockName {
_GLSL_BLOCK_RE = re.compile(
    r'layout\s*\([^)]*\)\s*(?:readonly\s+|writeonly\s+)?(?:uniform|buffer)\s+(\w+)\s*\{([^}]*)\}',
    re.MULTILINE | re.DOTALL,
)
# #define NAME value
_GLSL_DEFINE_RE = re.compile(
    r'^\s*#define\s+(\w+)(?:\s+(.+?))?$', re.MULTILINE
)
# push_constant block
_GLSL_PUSH_CONST_RE = re.compile(
    r'layout\s*\(\s*push_constant\s*\)\s*uniform\s+(\w+)\s*\{([^}]*)\}',
    re.MULTILINE | re.DOTALL,
)
# void main() or subroutine functions
_GLSL_FUNC_RE = re.compile(
    r'(?:^|\n)\s*(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{',
    re.MULTILINE,
)


def _index_glsl_file(file_path: str) -> list[MemoryEntry]:
    """Index a GLSL compute shader — layout bindings, push constants, defines."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    clean = _strip_cpp_comments(source)
    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    blocks = []
    defines = []
    functions = []
    push_constants = []
    layouts = []

    # --- Layout qualifiers ---
    for m in _GLSL_LAYOUT_RE.finditer(clean):
        layouts.append(m.group(1).strip())

    # --- Uniform/buffer blocks ---
    for m in _GLSL_BLOCK_RE.finditer(clean):
        name = m.group(1)
        body = m.group(2).strip()
        blocks.append(name)
        # Extract fields
        fields = []
        for line in body.split(';'):
            line = line.strip()
            if line:
                fields.append(line)
        summary = f"buffer/uniform {name}"
        if fields:
            shown = fields[:8]
            summary += " { " + "; ".join(shown)
            if len(fields) > 8:
                summary += f"; ... +{len(fields) - 8}"
            summary += " }"
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=summary,
            keywords=_extract_keywords_from_strings([name] + fields[:5]),
            file_mtime=file_mtime,
        ))

    # --- Push constants ---
    for m in _GLSL_PUSH_CONST_RE.finditer(clean):
        name = m.group(1)
        body = m.group(2).strip()
        push_constants.append(name)
        fields = [l.strip() for l in body.split(';') if l.strip()]
        summary = f"push_constant {name}"
        if fields:
            summary += " { " + "; ".join(fields[:6]) + " }"
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=summary,
            keywords=_extract_keywords_from_strings([name, "push_constant"] + fields[:5]),
            file_mtime=file_mtime,
        ))

    # --- #define ---
    for m in _GLSL_DEFINE_RE.finditer(clean):
        name = m.group(1)
        value = (m.group(2) or "").strip()
        if name.startswith("GL_") or name in ("VULKAN",):
            continue
        defines.append(name)
        summary = f"#define {name}" + (f" {value}" if value and len(value) < 60 else "")
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=summary,
            keywords=_extract_keywords_from_strings([name]),
            file_mtime=file_mtime,
        ))

    # --- Functions (main, helpers) ---
    glsl_types = {'void', 'float', 'vec2', 'vec3', 'vec4', 'int', 'uint', 'ivec2',
                  'ivec3', 'ivec4', 'uvec2', 'uvec3', 'uvec4', 'mat2', 'mat3', 'mat4',
                  'bool', 'double', 'dvec2', 'dvec3', 'dvec4'}
    for m in _GLSL_FUNC_RE.finditer(clean):
        ret = m.group(1)
        name = m.group(2)
        params = m.group(3).strip()
        if ret not in glsl_types:
            continue
        functions.append(name)
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=f"{ret} {name}({params})",
            keywords=_extract_keywords_from_strings([name, ret, params]),
            file_mtime=file_mtime,
        ))

    # --- Module entry ---
    summary_parts = [f"GLSL shader: {path.name}"]
    if layouts:
        summary_parts.append("Layouts: " + ", ".join(layouts[:5]))
    top_syms = [f"block {b}" for b in blocks] + [f"fn {f}" for f in functions]
    if top_syms:
        summary_parts.append("Defines: " + ", ".join(top_syms))

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts),
        keywords=_extract_keywords_from_strings(
            [module_name, "glsl", "shader"] + blocks + functions + defines
        ),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# Markdown indexing — heading/section extraction
# ------------------------------------------------------------------

_MD_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
_MD_CODE_BLOCK_RE = re.compile(r'^```(\w*)\n(.*?)^```', re.MULTILINE | re.DOTALL)
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def _index_md_file(file_path: str) -> list[MemoryEntry]:
    """Index a Markdown file — extract headings as symbols with section content."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    # Parse headings with their positions
    headings = []
    for m in _MD_HEADING_RE.finditer(source):
        level = len(m.group(1))
        title = m.group(2).strip()
        headings.append((level, title, m.start(), m.end()))

    # Extract code block languages
    code_langs = set()
    for m in _MD_CODE_BLOCK_RE.finditer(source):
        lang = m.group(1)
        if lang:
            code_langs.add(lang)

    # Extract links
    links = []
    for m in _MD_LINK_RE.finditer(source):
        links.append(m.group(1))

    # Create entry for each heading with its content preview
    for i, (level, title, start, end) in enumerate(headings):
        # Content is from after heading to next heading of same/higher level
        next_pos = len(source)
        for j in range(i + 1, len(headings)):
            if headings[j][0] <= level:
                next_pos = headings[j][2]
                break
        content = source[end:next_pos].strip()
        preview = content[:300].strip() if content else ""

        summary = f"{'#' * level} {title}"
        if preview:
            summary += f"\n{preview}"

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, title, "note"),
            file_path=file_path,
            symbol_name=title,
            kind="note",
            summary=summary,
            keywords=_extract_keywords_from_strings([title, preview[:100]]),
            file_mtime=file_mtime,
        ))

    # Module entry
    summary_parts = [f"Markdown: {path.name}"]
    if headings:
        toc = [f"{'  ' * (h[0] - 1)}- {h[1]}" for h in headings[:15]]
        summary_parts.append("TOC:\n" + "\n".join(toc))
    if code_langs:
        summary_parts.append(f"Code blocks: {', '.join(sorted(code_langs))}")

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts),
        keywords=_extract_keywords_from_strings(
            [module_name, "markdown", "docs"] + [h[1] for h in headings]
        ),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# PDF indexing via pypdf
# ------------------------------------------------------------------


def _index_pdf_file(file_path: str) -> list[MemoryEntry]:
    """Index a PDF file — extract text per page, store sections as memories."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed — cannot index %s. Install with: pip install pypdf", file_path)
        return []

    path = Path(file_path)
    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        logger.debug("Failed to read PDF %s: %s", file_path, exc)
        return []

    num_pages = len(reader.pages)
    all_text_preview = []

    for page_num, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if not text:
            continue

        # Store each page as a note
        preview = text[:500]
        all_text_preview.append(text[:100])

        # Try to extract a section heading from the page
        first_line = text.split('\n')[0].strip()[:80]
        symbol_name = f"page_{page_num}"
        if first_line and len(first_line) < 80:
            symbol_name = f"p{page_num}: {first_line}"

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, f"page_{page_num}", "note"),
            file_path=file_path,
            symbol_name=symbol_name,
            kind="note",
            summary=preview,
            keywords=_extract_keywords_from_strings([preview[:200]]),
            file_mtime=file_mtime,
        ))

    # Module entry
    summary_parts = [f"PDF: {path.name} ({num_pages} pages)"]
    if all_text_preview:
        combined = " ".join(all_text_preview)[:400]
        summary_parts.append(f"Content preview: {combined}")

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts),
        keywords=_extract_keywords_from_strings(
            [module_name, "pdf", "document"] + [t[:50] for t in all_text_preview[:5]]
        ),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# TOML indexing
# ------------------------------------------------------------------


def _index_toml_file(file_path: str) -> list[MemoryEntry]:
    """Index a TOML file — extract tables and key-value pairs."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Use tomllib (3.11+) or tomli
    try:
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        data = tomllib.loads(source)
    except Exception as exc:
        logger.debug("Failed to parse TOML %s: %s", file_path, exc)
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    def _walk_toml(d: dict, prefix: str = "") -> list[tuple[str, str]]:
        """Walk TOML dict, return (key_path, summary) pairs."""
        items = []
        for k, v in d.items():
            key_path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                # Table — recurse
                sub_keys = list(v.keys())
                summary = f"[{key_path}] — keys: {', '.join(sub_keys[:10])}"
                if len(sub_keys) > 10:
                    summary += f" ... +{len(sub_keys) - 10}"
                items.append((key_path, summary))
                items.extend(_walk_toml(v, key_path))
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Array of tables
                items.append((key_path, f"[[{key_path}]] — {len(v)} entries"))
            else:
                val_str = str(v)
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                items.append((key_path, f"{key_path} = {val_str}"))
        return items

    toml_items = _walk_toml(data)

    # Create entries for top-level tables
    top_tables = [k for k in data.keys() if isinstance(data[k], dict)]
    for table_name in top_tables:
        table = data[table_name]
        sub_items = _walk_toml(table, table_name)
        summary_lines = [f"[{table_name}]"]
        for _, s in sub_items[:15]:
            summary_lines.append(f"  {s}")
        if len(sub_items) > 15:
            summary_lines.append(f"  ... +{len(sub_items) - 15} more")

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, table_name, "class"),
            file_path=file_path,
            symbol_name=table_name,
            kind="class",
            summary="\n".join(summary_lines),
            keywords=_extract_keywords_from_strings(
                [table_name] + list(data[table_name].keys())[:10]
            ),
            file_mtime=file_mtime,
        ))

    # Module entry
    top_keys = list(data.keys())
    summary_parts = [f"TOML: {path.name}"]
    summary_parts.append("Top-level keys: " + ", ".join(top_keys[:20]))

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts),
        keywords=_extract_keywords_from_strings([module_name, "toml", "config"] + top_keys),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# JSON indexing
# ------------------------------------------------------------------


def _index_json_file(file_path: str) -> list[MemoryEntry]:
    """Index a JSON file — extract top-level keys and structure."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    try:
        data = json_lib.loads(source)
    except (json_lib.JSONDecodeError, ValueError) as exc:
        logger.debug("Failed to parse JSON %s: %s", file_path, exc)
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem

    if isinstance(data, dict):
        top_keys = list(data.keys())

        # Create entries for top-level object keys that are dicts/lists
        for key in top_keys[:30]:
            val = data[key]
            if isinstance(val, dict):
                sub_keys = list(val.keys())
                summary = f"{key}: {{ {', '.join(sub_keys[:10])} }}"
                if len(sub_keys) > 10:
                    summary += f" ... +{len(sub_keys) - 10}"
            elif isinstance(val, list):
                summary = f"{key}: [{len(val)} items]"
                if val and isinstance(val[0], dict):
                    sample_keys = list(val[0].keys())
                    summary += f" each: {{ {', '.join(sample_keys[:8])} }}"
            else:
                val_str = str(val)
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                summary = f"{key} = {val_str}"

            entries.append(MemoryEntry(
                memory_id=make_memory_id(file_path, key, "note"),
                file_path=file_path,
                symbol_name=key,
                kind="note",
                summary=summary,
                keywords=_extract_keywords_from_strings([key]),
                file_mtime=file_mtime,
            ))

        summary_text = f"JSON object with {len(top_keys)} keys: {', '.join(top_keys[:20])}"
    elif isinstance(data, list):
        top_keys = []
        summary_text = f"JSON array with {len(data)} items"
        if data and isinstance(data[0], dict):
            sample_keys = list(data[0].keys())
            summary_text += f", each: {{ {', '.join(sample_keys[:10])} }}"
    else:
        top_keys = []
        summary_text = f"JSON scalar: {str(data)[:100]}"

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary=f"JSON: {path.name}\n{summary_text}",
        keywords=_extract_keywords_from_strings([module_name, "json"] + top_keys[:15]),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# YAML indexing
# ------------------------------------------------------------------


def _index_yaml_file(file_path: str) -> list[MemoryEntry]:
    """Index a YAML file — extract top-level keys and structure."""
    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml not installed — cannot index %s", file_path)
        return []

    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    try:
        data = yaml.safe_load(source)
    except Exception as exc:
        logger.debug("Failed to parse YAML %s: %s", file_path, exc)
        return []

    if not isinstance(data, dict):
        return []

    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem
    top_keys = list(data.keys())

    for key in top_keys[:30]:
        val = data[key]
        if isinstance(val, dict):
            sub_keys = list(val.keys())
            summary = f"{key}: {{ {', '.join(str(k) for k in sub_keys[:10])} }}"
        elif isinstance(val, list):
            summary = f"{key}: [{len(val)} items]"
        else:
            val_str = str(val)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            summary = f"{key}: {val_str}"

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, str(key), "note"),
            file_path=file_path,
            symbol_name=str(key),
            kind="note",
            summary=summary,
            keywords=_extract_keywords_from_strings([str(key)]),
            file_mtime=file_mtime,
        ))

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary=f"YAML: {path.name}\nTop-level keys: {', '.join(str(k) for k in top_keys[:20])}",
        keywords=_extract_keywords_from_strings([module_name, "yaml", "config"] + [str(k) for k in top_keys]),
        file_mtime=file_mtime,
    ))

    return entries


# ------------------------------------------------------------------
# CMake indexing
# ------------------------------------------------------------------

_CMAKE_PROJECT_RE = re.compile(r'project\s*\(\s*(\w+)', re.IGNORECASE)
_CMAKE_TARGET_RE = re.compile(
    r'(?:add_executable|add_library|add_custom_target)\s*\(\s*(\w+)',
    re.IGNORECASE,
)
_CMAKE_SET_RE = re.compile(
    r'set\s*\(\s*(\w+)\s+(.*?)\)', re.IGNORECASE | re.DOTALL
)
_CMAKE_FIND_RE = re.compile(
    r'find_package\s*\(\s*(\w+)', re.IGNORECASE
)
_CMAKE_OPTION_RE = re.compile(
    r'option\s*\(\s*(\w+)\s+"([^"]*)"', re.IGNORECASE
)
_CMAKE_FUNC_RE = re.compile(
    r'(?:function|macro)\s*\(\s*(\w+)', re.IGNORECASE
)
_CMAKE_LINK_RE = re.compile(
    r'target_link_libraries\s*\(\s*(\w+)\s+(.*?)\)',
    re.IGNORECASE | re.DOTALL,
)
_CMAKE_INCLUDE_RE = re.compile(
    r'(?:include|add_subdirectory)\s*\(\s*([^\s)]+)', re.IGNORECASE
)


def _index_cmake_file(file_path: str) -> list[MemoryEntry]:
    """Index a CMake file — targets, variables, find_package, options."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Strip comments
    clean = re.sub(r'#[^\n]*', '', source)
    file_mtime = os.path.getmtime(file_path)
    entries: list[MemoryEntry] = []
    module_name = path.stem if path.stem != "CMakeLists" else f"CMakeLists_{path.parent.name}"

    projects = []
    targets = []
    packages = []
    options = []
    functions = []
    variables = []

    # --- Projects ---
    for m in _CMAKE_PROJECT_RE.finditer(clean):
        projects.append(m.group(1))

    # --- Targets ---
    for m in _CMAKE_TARGET_RE.finditer(clean):
        name = m.group(1)
        targets.append(name)

        # Find linked libraries for this target
        libs = []
        for lm in _CMAKE_LINK_RE.finditer(clean):
            if lm.group(1) == name:
                lib_str = lm.group(2).strip()
                libs.extend(re.split(r'\s+', lib_str))
        libs = [l for l in libs if l and l not in ('PUBLIC', 'PRIVATE', 'INTERFACE')]

        summary = f"target: {name}"
        if libs:
            summary += f"\n  Links: {', '.join(libs[:10])}"

        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "class"),
            file_path=file_path,
            symbol_name=name,
            kind="class",
            summary=summary,
            keywords=_extract_keywords_from_strings([name, "target"] + libs[:5]),
            dependencies=libs[:10],
            file_mtime=file_mtime,
        ))

    # --- find_package ---
    for m in _CMAKE_FIND_RE.finditer(clean):
        packages.append(m.group(1))

    # --- Options ---
    for m in _CMAKE_OPTION_RE.finditer(clean):
        name = m.group(1)
        desc = m.group(2)
        options.append(name)
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=f"option({name} \"{desc}\")",
            keywords=_extract_keywords_from_strings([name, desc]),
            file_mtime=file_mtime,
        ))

    # --- Functions/macros ---
    for m in _CMAKE_FUNC_RE.finditer(clean):
        name = m.group(1)
        functions.append(name)
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "function"),
            file_path=file_path,
            symbol_name=name,
            kind="function",
            summary=f"cmake function/macro {name}()",
            keywords=_extract_keywords_from_strings([name, "cmake"]),
            file_mtime=file_mtime,
        ))

    # --- Key variables (set) ---
    for m in _CMAKE_SET_RE.finditer(clean):
        name = m.group(1)
        value = m.group(2).strip()
        # Skip internal variables
        if name.startswith('_') or name.startswith('CMAKE_') and name not in (
            'CMAKE_CXX_STANDARD', 'CMAKE_C_STANDARD', 'CMAKE_BUILD_TYPE'
        ):
            continue
        variables.append(name)
        val_preview = value[:60] if value else ""
        entries.append(MemoryEntry(
            memory_id=make_memory_id(file_path, name, "note"),
            file_path=file_path,
            symbol_name=name,
            kind="note",
            summary=f"set({name} {val_preview})",
            keywords=_extract_keywords_from_strings([name]),
            file_mtime=file_mtime,
        ))

    # --- Includes/subdirectories ---
    includes = [m.group(1) for m in _CMAKE_INCLUDE_RE.finditer(clean)]

    # Module entry
    summary_parts = [f"CMake: {path.name}"]
    if projects:
        summary_parts.append(f"Project: {', '.join(projects)}")
    if targets:
        summary_parts.append(f"Targets: {', '.join(targets)}")
    if packages:
        summary_parts.append(f"Packages: {', '.join(packages)}")
    if includes:
        summary_parts.append(f"Includes: {', '.join(includes[:10])}")

    entries.insert(0, MemoryEntry(
        memory_id=make_memory_id(file_path, module_name, "module"),
        file_path=file_path,
        symbol_name=module_name,
        kind="module",
        summary="\n".join(summary_parts),
        keywords=_extract_keywords_from_strings(
            [module_name, "cmake", "build"] + targets + packages + projects
        ),
        dependencies=packages + includes,
        file_mtime=file_mtime,
    ))

    return entries


# Common words that don't help discriminate code symbols
_STOP_WORDS = frozenset(
    {
        "the",
        "is",
        "in",
        "of",
        "to",
        "and",
        "or",
        "for",
        "if",
        "not",
        "with",
        "as",
        "from",
        "by",
        "on",
        "at",
        "be",
        "it",
        "an",
        "no",
        "do",
        "self",
        "cls",
        "none",
        "true",
        "false",
        "return",
        "def",
        "class",
        "import",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "type",
        "any",
        "optional",
    }
)
