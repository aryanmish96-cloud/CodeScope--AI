"""
repo_search.py – Fast local candidate retrieval for CodeScope AI.

Uses the RepoIndex built by repo_indexer.py.
No Groq/AI calls. No external APIs. Pure deterministic scoring.

Repository isolation: all operations take a repo_index argument scoped to one session.
Results from repo A can never appear in repo B.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from repo_indexer import RepoIndex, SymbolRecord


# ── Concept Synonym Map ───────────────────────────────────────────────────────

CONCEPT_SYNONYMS: dict[str, list[str]] = {
    "login": [
        "signin", "sign_in", "log_in", "authenticate", "authentication",
        "auth", "credential", "credentials", "password", "passwd", "pwd",
        "verify_password", "check_password", "bcrypt", "token", "jwt",
        "session", "login", "logon",
    ],
    "logout": ["signout", "sign_out", "log_out", "revoke", "invalidate_token", "logout"],
    "register": [
        "signup", "sign_up", "create_account", "create_user",
        "register", "registration", "new_user",
    ],
    "password": [
        "password", "passwd", "pwd", "bcrypt", "hash_password",
        "check_password", "verify_password", "encrypt",
    ],
    "token": [
        "token", "jwt", "access_token", "refresh_token", "bearer",
        "create_token", "generate_token", "encode", "decode",
    ],
    "database": [
        "database", "db", "orm", "query", "model", "repository",
        "dao", "schema", "migration", "connection", "connect",
        "sql", "mongodb", "postgres", "mysql", "sqlite",
    ],
    "api": [
        "route", "endpoint", "handler", "controller", "router",
        "api", "rest", "graphql", "grpc",
    ],
    "middleware": ["middleware", "interceptor", "filter", "guard", "hook", "pipe"],
    "config": [
        "config", "configuration", "settings", "env", "environment",
        "constants", "options",
    ],
    "test": ["test", "spec", "unittest", "pytest", "jest", "assert", "mock"],
    "error": ["error", "exception", "handler", "catch", "raise", "throw", "err"],
    "upload": ["upload", "file", "multipart", "storage", "s3", "bucket", "blob"],
    "email": ["email", "mail", "smtp", "send_email", "mailer", "sendgrid"],
    "cache": ["cache", "redis", "memcache", "ttl", "expire", "invalidate"],
    "user": ["user", "profile", "account", "member", "customer", "principal"],
    "payment": ["payment", "stripe", "paypal", "charge", "billing", "invoice"],
    "websocket": ["websocket", "ws", "socket", "realtime", "event", "broadcast"],
}

# Files that are documentation/low priority for implementation queries
_DOC_PATH_MARKERS = {
    "readme", "changelog", "license", ".md", "docs/",
    "documentation/", "examples/", "wiki/",
}
_TEST_PATH_MARKERS = {"test", "spec", "__test__", "tests/", ".test.", ".spec."}


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class Candidate:
    """A ranked candidate from local repository search."""
    id: str                         # Short ID used in Groq prompt (S1, S2, ...)
    internal_id: str                # Original SYM_N or FILE:path id
    score: float
    file: str
    symbol: str | None              # Symbol/function name if applicable
    start_line: int
    end_line: int
    match_reasons: list[str] = field(default_factory=list)
    snippet: str = ""               # Actual code snippet (retrieved from files on demand)
    route_path: str | None = None
    sym_type: str = ""              # "function" | "class" | "method" | "route" | "file"
    language: str = ""


@dataclass
class SearchResult:
    """Result of a local repository search operation."""
    candidates: list[Candidate]
    query_expanded: list[str]       # Expanded query terms (for transparency)
    not_found: bool = False


# ── Query Expansion ───────────────────────────────────────────────────────────

def _expand_query(query: str) -> set[str]:
    """
    Expand query into a set of related terms using the synonym map.
    Deterministic – no AI calls.
    """
    q_lower = query.lower()
    terms: set[str] = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", q_lower))

    for concept, synonyms in CONCEPT_SYNONYMS.items():
        # If the query contains the concept OR any primary synonym
        if concept in q_lower or any(s in q_lower for s in synonyms[:4]):
            terms.update(synonyms)

    return terms


# ── Source Priority Helpers ───────────────────────────────────────────────────

def _doc_penalty(path: str) -> float:
    """Return a multiplier < 1.0 for documentation files."""
    p = path.lower()
    if any(d in p for d in _DOC_PATH_MARKERS):
        return 0.25
    return 1.0


def _is_test_file(path: str) -> bool:
    p = path.lower()
    return any(t in p for t in _TEST_PATH_MARKERS)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_symbol(
    sym: SymbolRecord,
    query_terms: set[str],
    current_file: str | None,
    mode: str,
    intent_is_implementation: bool,
) -> tuple[float, list[str]]:
    """
    Score a symbol against the query.
    Returns (score, match_reasons).
    Score is NOT treated as a confidence percentage – it is a retrieval signal.
    """
    score = 0.0
    reasons: list[str] = []
    name_lower = sym.name.lower()
    sig_lower = sym.signature.lower()
    file_lower = sym.file.lower()

    for term in query_terms:
        if not term or len(term) < 2:
            continue

        # Exact symbol name match (highest signal)
        if name_lower == term:
            score += 1.0
            reasons.append(f"exact symbol name match: '{sym.name}'")

        # Symbol name contains term
        elif term in name_lower and len(term) >= 3:
            score += 0.75
            if not any("symbol" in r for r in reasons):
                reasons.append(f"symbol '{sym.name}' contains '{term}'")

        # Route path match (high signal)
        if sym.route_path:
            rp = sym.route_path.lower()
            if term == rp or term in rp:
                score += 0.9
                reasons.append(f"route path '{sym.route_path}' matches '{term}'")

        # Signature keyword match
        if term in sig_lower and len(term) >= 3:
            score += 0.35
            if not any("signature" in r for r in reasons):
                reasons.append(f"signature contains '{term}'")

        # File path match
        if term in file_lower and len(term) >= 3:
            score += 0.55
            if not any("file path" in r for r in reasons):
                reasons.append(f"file '{sym.file.split('/')[-1]}' matches '{term}'")

    # Current file bonus
    if current_file and sym.file == current_file:
        if mode == "file":
            score += 0.5
            reasons.append("symbol in currently open file")
        else:
            score += 0.15

    # Source file vs documentation priority
    penalty = _doc_penalty(sym.file)
    if penalty < 1.0:
        score *= penalty

    # Test file: slight penalty for implementation questions, not for test questions
    if intent_is_implementation and _is_test_file(sym.file):
        score *= 0.7

    return score, reasons


def _retrieve_snippet(files: dict, file_path: str, start_line: int, end_line: int, ctx: int = 3) -> str:
    """Retrieve actual code from file content without re-reading disk."""
    file_data = files.get(file_path, {})
    content = file_data.get("content", "")
    if not content:
        return ""
    lines = content.split("\n")
    s = max(0, start_line - 1 - ctx)
    e = min(len(lines), end_line + ctx)
    return "\n".join(lines[s:e])


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    """Remove overlapping line ranges in the same file, keeping higher-scored."""
    seen_ranges: dict[str, list[tuple[int, int]]] = {}
    result: list[Candidate] = []

    for c in candidates:
        ranges = seen_ranges.get(c.file, [])
        is_duplicate = False
        for s, e in ranges:
            overlap_s = max(c.start_line, s)
            overlap_e = min(c.end_line, e)
            if overlap_e >= overlap_s:
                c_size = max(1, c.end_line - c.start_line + 1)
                overlap_size = overlap_e - overlap_s + 1
                if overlap_size / c_size > 0.6:
                    is_duplicate = True
                    break
        if not is_duplicate:
            result.append(c)
            seen_ranges.setdefault(c.file, []).append((c.start_line, c.end_line))

    return result


# ── Context Budget Enforcement ────────────────────────────────────────────────

def _enforce_budget(candidates: list[Candidate], files: dict, token_budget: int = 3500) -> None:
    """
    Trim snippets to fit within the Groq context budget.
    Modifies candidates in-place.
    Prefer 5-8 highly relevant snippets over 50+ weak ones.
    """
    char_budget = token_budget * 4  # ~4 chars per token
    total = 0

    for c in candidates:
        if not c.snippet:
            c.snippet = _retrieve_snippet(files, c.file, c.start_line, c.end_line)

        remaining = char_budget - total
        if remaining <= 0:
            # Budget exhausted: include only the signature line
            file_data = files.get(c.file, {})
            content = file_data.get("content", "")
            if content:
                sig_line = content.split("\n")[max(0, c.start_line - 1)]
                c.snippet = sig_line.strip() + "\n    # ... (omitted – budget)"
            else:
                c.snippet = "# [omitted – context budget]"
        elif len(c.snippet) > remaining:
            c.snippet = c.snippet[:remaining] + "\n    # ... (truncated)"

        total += len(c.snippet)


# ── Intent Detection ──────────────────────────────────────────────────────────

_LOCATION_TERMS = re.compile(
    r"\b(where|find|locate|show me|which file|which function|where does|where is|how to find)\b",
    re.IGNORECASE,
)
_IMPLEMENTATION_TERMS = re.compile(
    r"\b(how does|explain|implement|logic|flow|works|does it|run|execute)\b",
    re.IGNORECASE,
)


def _is_implementation_query(question: str) -> bool:
    return bool(_IMPLEMENTATION_TERMS.search(question)) and not bool(_LOCATION_TERMS.search(question))


# ── File-Level Fallback Search ────────────────────────────────────────────────

def _file_level_search(
    files: dict,
    query_terms: set[str],
    current_file: str | None,
    mode: str,
    impl_query: bool,
    counter: list[int],
) -> list[Candidate]:
    """
    Search raw file content for repos or files without symbol extraction.
    Used as a fallback when symbol search yields no results.
    """
    candidates: list[Candidate] = []
    files_with_results: set[str] = set()

    for path, file_data in files.items():
        content = file_data.get("content", "")
        if not content:
            continue
        content_lower = content.lower()

        score = 0.0
        reasons: list[str] = []

        for term in query_terms:
            if not term or len(term) < 3:
                continue
            if term in content_lower:
                count = min(content_lower.count(term), 5)
                score += 0.3 + count * 0.04
                if not any(term in r for r in reasons):
                    reasons.append(f"file contains '{term}'")

        if current_file and path == current_file and mode == "file":
            score += 0.5
            reasons.insert(0, "currently open file")

        # Apply doc penalty
        score *= _doc_penalty(path)
        if impl_query and _is_test_file(path):
            score *= 0.7

        if score > 0.2:
            # Find the line with the best keyword match
            best_line = 1
            for i, line in enumerate(content.split("\n")):
                ll = line.lower()
                if any(t in ll for t in query_terms if t and len(t) >= 3):
                    best_line = i + 1
                    break

            lines_total = file_data.get("lines", content.count("\n") + 1)
            snippet = _retrieve_snippet(files, path, best_line, min(best_line + 20, lines_total))

            cid = f"FC_{counter[0]}"
            counter[0] += 1
            candidates.append(
                Candidate(
                    id=cid, internal_id=f"FILE:{path}",
                    score=score, file=path, symbol=None,
                    start_line=best_line, end_line=min(best_line + 20, lines_total),
                    match_reasons=reasons, snippet=snippet, sym_type="file",
                )
            )
            files_with_results.add(path)

    return candidates


# ── Evidence Label ────────────────────────────────────────────────────────────

def compute_evidence_label(candidates: list[Candidate]) -> str:
    """
    Compute a human-readable evidence label from retrieval signals.
    NEVER treats raw score as a percentage.
    """
    if not candidates:
        return "No evidence"

    best_score = candidates[0].score
    all_reasons = [r for c in candidates[:3] for r in c.match_reasons]

    has_exact = any("exact symbol name match" in r for r in all_reasons)
    has_route = any("route path" in r or "route" in r for r in all_reasons)
    has_current_file = any("currently open file" in r for r in all_reasons)

    if has_exact or has_route or (has_current_file and best_score >= 0.7):
        return "Strong evidence"
    if best_score >= 0.55 or (len(candidates) >= 2 and best_score >= 0.4):
        return "Moderate evidence"
    return "Weak evidence"


# ── Main Search Entry Point ───────────────────────────────────────────────────

def search_repository(
    repo_index: RepoIndex,
    files: dict,
    query: str,
    mode: str = "repo",
    current_file: str | None = None,
    max_candidates: int = 8,
    not_found_threshold: float = 0.25,
) -> SearchResult:
    """
    Fast local candidate retrieval from the repository index.

    Repository isolation: operates exclusively on the provided repo_index.
    No Groq calls. No cross-repo contamination possible.

    Args:
        repo_index: The RepoIndex for the current session (scoped to one repo).
        files:      The files dict from the session (same scope).
        query:      The user's natural language question.
        mode:       "file" | "flow" | "repo"
        current_file: Currently open file path (for FILE mode fast path).
        max_candidates: Maximum number of candidates to return (default 8).
        not_found_threshold: Minimum score to include a result.

    Returns:
        SearchResult with ranked candidates, each containing a real code snippet.
    """
    query_terms = _expand_query(query)
    impl_query = _is_implementation_query(query)

    # ── FILE MODE FAST PATH ─────────────────────────────────────────────────
    # If we're in file mode with a current file, search it first.
    # If we get strong evidence, skip the expensive repo-wide search.
    if mode == "file" and current_file:
        file_sym_ids = repo_index.file_index.get(current_file, [])
        file_candidates: list[Candidate] = []

        for sym_id in file_sym_ids:
            sym = repo_index.by_id.get(sym_id)
            if not sym:
                continue
            score, reasons = _score_symbol(sym, query_terms, current_file, mode, impl_query)
            if score > 0:
                snippet = _retrieve_snippet(files, sym.file, sym.start_line, sym.end_line)
                file_candidates.append(
                    Candidate(
                        id=sym.id, internal_id=sym.id,
                        score=score, file=sym.file,
                        symbol=sym.name, start_line=sym.start_line, end_line=sym.end_line,
                        match_reasons=reasons, snippet=snippet,
                        route_path=sym.route_path, sym_type=sym.type, language=sym.language,
                    )
                )

        # Also add the whole file as a candidate (for general file-level questions)
        file_data = files.get(current_file, {})
        fc = file_data.get("content", "")
        if fc:
            fc_score = 0.0
            fc_reasons: list[str] = ["currently open file"]
            for term in query_terms:
                if term and len(term) >= 3 and term in fc.lower():
                    fc_score += 0.3
                    fc_reasons.append(f"file contains '{term}'")
            if fc_score > 0 or mode == "file":
                # Always include current file in FILE mode
                fc_score = max(fc_score, 0.5)
                file_candidates.append(
                    Candidate(
                        id=f"FILE:{current_file}", internal_id=f"FILE:{current_file}",
                        score=fc_score, file=current_file, symbol=None,
                        start_line=1, end_line=file_data.get("lines", 1),
                        match_reasons=fc_reasons,
                        snippet=fc[:2500],  # first 2500 chars for context
                        sym_type="file",
                    )
                )

        file_candidates.sort(key=lambda c: c.score, reverse=True)
        file_candidates = _deduplicate(file_candidates)

        # If best score is strong, skip repo-wide search
        if file_candidates and file_candidates[0].score >= 0.6:
            top = file_candidates[:max_candidates]
            _enforce_budget(top, files)
            return SearchResult(
                candidates=top,
                query_expanded=list(query_terms),
            )

    # ── REPOSITORY-WIDE SEARCH ──────────────────────────────────────────────
    all_candidates: list[Candidate] = []

    for sym in repo_index.symbols:
        score, reasons = _score_symbol(sym, query_terms, current_file, mode, impl_query)
        if score <= 0.05:
            continue
        snippet = _retrieve_snippet(files, sym.file, sym.start_line, sym.end_line)
        all_candidates.append(
            Candidate(
                id=sym.id, internal_id=sym.id,
                score=score, file=sym.file,
                symbol=sym.name, start_line=sym.start_line, end_line=sym.end_line,
                match_reasons=reasons, snippet=snippet,
                route_path=sym.route_path, sym_type=sym.type, language=sym.language,
            )
        )

    # Add file-level fallback for files without extractors or to supplement
    fc_counter = [len(repo_index.symbols) + 10000]
    files_already_covered = {c.file for c in all_candidates}
    file_level = _file_level_search(
        files, query_terms, current_file, mode, impl_query, fc_counter
    )
    for fc in file_level:
        if fc.file not in files_already_covered:
            all_candidates.append(fc)

    # Sort by score descending
    all_candidates.sort(key=lambda c: c.score, reverse=True)

    # Deduplicate overlapping ranges
    all_candidates = _deduplicate(all_candidates)

    # NOT_FOUND: if best score is too low, return empty
    if not all_candidates or all_candidates[0].score < not_found_threshold:
        return SearchResult(
            candidates=[],
            query_expanded=list(query_terms),
            not_found=True,
        )

    # Keep top N candidates and enforce context budget
    top = all_candidates[:max_candidates]
    _enforce_budget(top, files)

    return SearchResult(candidates=top, query_expanded=list(query_terms))
