"""
repo_indexer.py – Deterministic, Groq-free symbol extraction for CodeScope AI.

Called ONCE per repository session (during the analysis pipeline).
Results are cached in _repo_indexes[session_id] in main.py.
No AI calls. No external APIs. Pure regex-based parsing.

IMPORTANT: This module must NEVER be imported or called inside /chat request handlers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class SymbolRecord:
    """
    Lightweight symbol record.
    The full symbol body is NOT stored here to avoid memory duplication.
    Retrieve actual code via:
        files[file]["content"].split('\\n')[start_line-1:end_line]
    """
    id: str
    file: str
    type: str           # "function" | "class" | "method" | "route" | "export"
    name: str
    start_line: int     # 1-indexed, inclusive
    end_line: int       # 1-indexed, inclusive
    language: str
    signature: str      # First meaningful line only – no full body duplication
    route_path: str | None = None  # e.g. "/auth/login" for HTTP route symbols


@dataclass
class RepoIndex:
    """
    In-memory repository symbol index.
    Built ONCE per session, stored in _repo_indexes[session_id] in main.py.
    Reused for every subsequent /chat call on that session.
    Never rebuilt inside request handlers.
    """
    session_id: str
    symbols: list[SymbolRecord] = field(default_factory=list)

    # Fast lookup structures (all keyed by string for speed)
    by_id: dict[str, SymbolRecord] = field(default_factory=dict)
    file_index: dict[str, list[str]] = field(default_factory=dict)     # file → [sym_ids]
    name_index: dict[str, list[str]] = field(default_factory=dict)     # name.lower() → [sym_ids]
    keyword_index: dict[str, list[str]] = field(default_factory=dict)  # word → [sym_ids | "FILE:path"]
    route_index: dict[str, str] = field(default_factory=dict)          # "/route/path" → sym_id


# ── Language Detection Patterns ───────────────────────────────────────────────

# Python
_PY_FUNC = re.compile(r'^( *)(async +)?def +(\w+) *\(', re.MULTILINE)
_PY_CLASS = re.compile(r'^( *)class +(\w+)[ :(]', re.MULTILINE)
_PY_ROUTE = re.compile(
    r"""@(?:[\w]+\.)*(?:get|post|put|delete|patch|options|head|websocket) *\( *['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# JavaScript / TypeScript
_JS_FUNC = re.compile(r'^\s*(?:export +)?(?:async +)?function +(\w+) *\(', re.MULTILINE)
_JS_ARROW = re.compile(r'^\s*(?:export +)?(?:const|let|var) +(\w+) *= *(?:async +)?\(', re.MULTILINE)
_JS_CLASS = re.compile(r'^\s*(?:export +)?(?:abstract +)?class +(\w+)', re.MULTILINE)
_JS_ROUTE = re.compile(
    r"""(?:router|app|server)\.(?:get|post|put|delete|patch|all|use) *\( *['"`]([^'"`]+)['"`]""",
    re.IGNORECASE,
)
_JSX_COMPONENT = re.compile(r'^\s*(?:export +)?(?:default +)?function +([A-Z]\w+) *\(', re.MULTILINE)

# Java
_JAVA_CLASS = re.compile(
    r'^\s*(?:public |private |protected |abstract |final |static )*class +(\w+)',
    re.MULTILINE,
)
_JAVA_METHOD = re.compile(
    r'^\s+(?:(?:public|private|protected|static|final|synchronized|abstract|native|transient)\s+)*'
    r'(?:[\w<>\[\],\s]+\s+)?(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{',
    re.MULTILINE,
)
_JAVA_ROUTE = re.compile(
    r'@(?:Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)

# Go
_GO_FUNC = re.compile(r'^func +(?:\(\w+ +\*?\w+\) +)?(\w+) *\(', re.MULTILINE)

# Rust
_RUST_FN = re.compile(r'^\s*(?:pub(?:\s*\(\w+\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]', re.MULTILINE)


# ── Path Filtering ────────────────────────────────────────────────────────────

_SKIP_PATH_FRAGMENTS = {
    "node_modules/", ".venv/", "venv/", "dist/", "build/",
    "__pycache__/", ".git/", "coverage/", ".next/", "target/",
    ".cache/", "vendor/", ".eggs/", "eggs/",
}

_DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
_DOC_PATH_MARKERS = {
    "readme", "changelog", "license", "docs/", "documentation/",
    "examples/", "wiki/",
}

_STOP_WORDS = {
    "the", "and", "for", "are", "this", "that", "with", "from", "not", "def",
    "class", "self", "return", "import", "function", "const", "let", "var",
    "public", "private", "static", "void", "async", "await", "true", "false",
    "none", "null", "undefined", "int", "str", "bool", "list", "dict", "type",
    "else", "elif", "while", "pass", "raise", "except", "try", "finally",
}


# ── Block End Heuristics ──────────────────────────────────────────────────────

def _py_block_end(lines: list[str], start_idx: int) -> int:
    """Find the last line (1-indexed) of a Python indented block."""
    if start_idx >= len(lines):
        return start_idx + 1
    # Determine base indent from the definition line itself
    base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip()) if lines[start_idx].strip() else 0
    end_idx = start_idx
    for i in range(start_idx + 1, min(start_idx + 300, len(lines))):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            end_idx = i  # blank/comment lines extend the block
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and stripped:
            break  # back to same or higher level = block ended
        end_idx = i
    return end_idx + 1  # convert to 1-indexed


def _brace_block_end(lines: list[str], start_idx: int) -> int:
    """Find the end of a brace-delimited block (JS/Java/Go/Rust)."""
    depth = 0
    for i in range(start_idx, min(start_idx + 250, len(lines))):
        depth += lines[i].count("{") - lines[i].count("}")
        if i > start_idx and depth <= 0:
            return i + 1  # 1-indexed
    return min(start_idx + 80, len(lines))


# ── Language-Specific Extractors ──────────────────────────────────────────────

def _extract_python(path: str, content: str, counter: list[int]) -> list[SymbolRecord]:
    lines = content.split("\n")
    symbols: list[SymbolRecord] = []
    seen_lines: set[int] = set()

    # Pre-build route decorator map: line_idx (0-based) → route path
    route_map: dict[int, str] = {}
    for m in _PY_ROUTE.finditer(content):
        li = content[: m.start()].count("\n")
        route_map[li] = m.group(1)

    # Extract function definitions
    for m in _PY_FUNC.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        seen_lines.add(li)

        indent_str = m.group(1) or ""
        indent = len(indent_str)
        name = m.group(3)
        start_ln = li + 1  # 1-indexed

        # Check for route decorator in preceding 8 lines
        route_path: str | None = None
        for di in range(max(0, li - 8), li):
            if di in route_map:
                route_path = route_map[di]
                start_ln = di + 1  # highlight from decorator line
                break

        end_ln = _py_block_end(lines, li)
        sig = lines[li].strip() if li < len(lines) else name

        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path,
                type="route" if route_path else ("method" if indent >= 4 else "function"),
                name=name, start_line=start_ln, end_line=end_ln,
                language="python", signature=sig, route_path=route_path,
            )
        )

    # Extract class definitions
    for m in _PY_CLASS.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        seen_lines.add(li)
        name = m.group(2)
        end_ln = _py_block_end(lines, li)
        sig = lines[li].strip() if li < len(lines) else name

        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path, type="class",
                name=name, start_line=li + 1, end_line=end_ln,
                language="python", signature=sig,
            )
        )

    return symbols


def _extract_js(path: str, content: str, counter: list[int]) -> list[SymbolRecord]:
    lines = content.split("\n")
    symbols: list[SymbolRecord] = []
    seen_lines: set[int] = set()
    lang = "typescript" if path.endswith((".ts", ".tsx")) else "javascript"

    # Function declarations, arrow const functions, classes
    for pattern, sym_type in [
        (_JSX_COMPONENT, "class"),   # React components (capitalized) first
        (_JS_FUNC, "function"),
        (_JS_ARROW, "function"),
        (_JS_CLASS, "class"),
    ]:
        for m in pattern.finditer(content):
            li = content[: m.start()].count("\n")
            if li in seen_lines:
                continue
            seen_lines.add(li)
            name = m.group(1)
            end_ln = _brace_block_end(lines, li)
            sig = lines[li].strip() if li < len(lines) else name

            sym_id = f"SYM_{counter[0]}"
            counter[0] += 1
            symbols.append(
                SymbolRecord(
                    id=sym_id, file=path, type=sym_type,
                    name=name, start_line=li + 1, end_line=end_ln,
                    language=lang, signature=sig,
                )
            )

    # Route definitions (Express/Fastify style)
    for m in _JS_ROUTE.finditer(content):
        li = content[: m.start()].count("\n")
        route_path = m.group(1)
        sig = lines[li].strip() if li < len(lines) else route_path

        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path, type="route",
                name=route_path, start_line=li + 1,
                end_line=min(li + 20, len(lines)),
                language=lang, signature=sig, route_path=route_path,
            )
        )

    return symbols


def _extract_java(path: str, content: str, counter: list[int]) -> list[SymbolRecord]:
    lines = content.split("\n")
    symbols: list[SymbolRecord] = []
    seen_lines: set[int] = set()
    _JAVA_KW = {"if", "while", "for", "switch", "catch", "try", "else", "do"}

    for m in _JAVA_CLASS.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        seen_lines.add(li)
        name = m.group(1)
        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path, type="class",
                name=name, start_line=li + 1,
                end_line=min(li + 150, len(lines)),
                language="java",
                signature=lines[li].strip() if li < len(lines) else name,
            )
        )

    for m in _JAVA_METHOD.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        name = m.group(1)
        if name in _JAVA_KW:
            continue
        seen_lines.add(li)

        route_path: str | None = None
        for di in range(max(0, li - 5), li):
            rm = _JAVA_ROUTE.search(lines[di] if di < len(lines) else "")
            if rm:
                route_path = rm.group(1)
                break

        end_ln = _brace_block_end(lines, li)
        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path,
                type="route" if route_path else "method",
                name=name, start_line=li + 1, end_line=end_ln,
                language="java",
                signature=lines[li].strip() if li < len(lines) else name,
                route_path=route_path,
            )
        )

    return symbols


def _extract_go(path: str, content: str, counter: list[int]) -> list[SymbolRecord]:
    lines = content.split("\n")
    symbols: list[SymbolRecord] = []
    seen_lines: set[int] = set()

    for m in _GO_FUNC.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        seen_lines.add(li)
        name = m.group(1)
        if name in {"init", "main"} or name[0].islower() is False:
            pass  # keep all Go functions including unexported
        end_ln = _brace_block_end(lines, li)
        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path, type="function",
                name=name, start_line=li + 1, end_line=end_ln,
                language="go",
                signature=lines[li].strip() if li < len(lines) else name,
            )
        )

    return symbols


def _extract_rust(path: str, content: str, counter: list[int]) -> list[SymbolRecord]:
    lines = content.split("\n")
    symbols: list[SymbolRecord] = []
    seen_lines: set[int] = set()

    for m in _RUST_FN.finditer(content):
        li = content[: m.start()].count("\n")
        if li in seen_lines:
            continue
        seen_lines.add(li)
        name = m.group(1)
        end_ln = _brace_block_end(lines, li)
        sym_id = f"SYM_{counter[0]}"
        counter[0] += 1
        symbols.append(
            SymbolRecord(
                id=sym_id, file=path, type="function",
                name=name, start_line=li + 1, end_line=end_ln,
                language="rust",
                signature=lines[li].strip() if li < len(lines) else name,
            )
        )

    return symbols


_EXTRACTORS: dict[str, Any] = {
    ".py": _extract_python,
    ".js": _extract_js,
    ".jsx": _extract_js,
    ".ts": _extract_js,
    ".tsx": _extract_js,
    ".java": _extract_java,
    ".go": _extract_go,
    ".rs": _extract_rust,
}


# ── Keyword Indexing ──────────────────────────────────────────────────────────

def _index_text(text: str, ref: str, keyword_index: dict[str, list[str]]) -> None:
    """Add non-trivial words from `text` to the inverted index under `ref`."""
    for word in set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())):
        if word not in _STOP_WORDS:
            lst = keyword_index.setdefault(word, [])
            if ref not in lst:
                lst.append(ref)


def _should_skip(path: str) -> bool:
    p = path.lower()
    return any(frag in p for frag in _SKIP_PATH_FRAGMENTS)


# ── Public API ────────────────────────────────────────────────────────────────

def build_symbol_index(files: dict[str, dict], session_id: str = "") -> RepoIndex:
    """
    Build a lightweight symbol index from already-parsed file content.

    This function is called ONCE per session during the analysis pipeline.
    It MUST NOT be called inside /chat request handlers.

    Design principles:
    - Symbol records do NOT store full bodies (only start_line/end_line + signature).
      Actual code is retrieved on-demand from files[path]["content"].
    - No Groq calls. No external APIs. Pure deterministic parsing.
    - Operates within the scope of the provided `files` dict (repo isolation).

    Returns a RepoIndex used by search_repository() in repo_search.py.
    """
    index = RepoIndex(session_id=session_id)
    counter = [0]  # mutable counter for globally unique symbol IDs

    for path, file_data in files.items():
        if _should_skip(path):
            continue
        content = file_data.get("content", "")
        if not content or not content.strip():
            continue

        ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
        extractor = _EXTRACTORS.get(ext)

        extracted: list[SymbolRecord] = []
        if extractor:
            try:
                extracted = extractor(path, content, counter)
            except Exception:
                extracted = []

        for sym in extracted:
            index.symbols.append(sym)
            index.by_id[sym.id] = sym
            index.file_index.setdefault(sym.file, []).append(sym.id)
            index.name_index.setdefault(sym.name.lower(), []).append(sym.id)

            if sym.route_path:
                index.route_index[sym.route_path] = sym.id
                _index_text(sym.route_path, sym.id, index.keyword_index)

            # Index symbol name + signature keywords (NOT full body)
            _index_text(sym.name + " " + sym.signature, sym.id, index.keyword_index)

        # File-level keyword index (for content search / files without extractors)
        # Only first 4 KB to keep indexing fast
        file_ref = f"FILE:{path}"
        _index_text(content[:4000], file_ref, index.keyword_index)

    return index
