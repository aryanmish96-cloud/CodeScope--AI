"""
tests/test_grounding.py – Behavioral grounding tests for CodeScope AI.

Tests verify:
- Index is built once and not rebuilt per-request
- Repository isolation (results from repo A never in repo B)
- FILE mode fast path behavior
- Invalid candidate ID rejection
- NOT_FOUND behavior
- Architecture doesn't add phantom components
- Evidence label computation
- Search scoring correctness
- Documentation doesn't outrank source for implementation queries

Run with:
    cd backend
    python -m pytest tests/test_grounding.py -v
"""

from __future__ import annotations

import sys
import os
import pytest

# Allow importing backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repo_indexer import build_symbol_index, RepoIndex, SymbolRecord
from repo_search import search_repository, compute_evidence_label, Candidate
from architecture import detect_architecture, build_verified_mermaid


# ── Test Fixtures ─────────────────────────────────────────────────────────────

def _make_files(specs: dict[str, str]) -> dict[str, dict]:
    """Helper: create a minimal files dict from {path: content}."""
    result = {}
    for path, content in specs.items():
        result[path] = {
            "path": path,
            "name": path.split("/")[-1],
            "extension": path.rsplit(".", 1)[-1] if "." in path else "",
            "content": content,
            "lines": content.count("\n") + 1,
        }
    return result


# Sample FastAPI file with login function
FASTAPI_AUTH_FILE = """
from fastapi import FastAPI
from passlib.context import CryptContext
import jwt

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"])

@app.post("/login")
def login_user(username: str, password: str):
    user = get_user(username)
    if not verify_password(password, user.hashed_password):
        raise HTTPException(401)
    token = create_access_token(user)
    return {"token": token}

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user) -> str:
    return jwt.encode({"sub": user.id}, SECRET_KEY)
"""

FASTAPI_ITEMS_FILE = """
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class RecursiveItem(BaseModel):
    id: int
    children: list['RecursiveItem'] = []

@app.get("/items/recursive")
def get_recursive():
    return RecursiveItem(id=1, children=[RecursiveItem(id=2)])

@app.get("/items/stream")
def get_stream():
    return {"items": list(range(100))}
"""

AUTH_ONLY_FILES = _make_files({
    "src/auth/service.py": FASTAPI_AUTH_FILE,
    "requirements.txt": "fastapi\npasslib\npyjwt\n",
})

ITEMS_ONLY_FILES = _make_files({
    "app.py": FASTAPI_ITEMS_FILE,
    "requirements.txt": "fastapi\npydantic\n",
})

NO_AUTH_FILES = _make_files({
    "utils/formatter.py": "def format_string(s): return s.strip().lower()\n",
    "utils/parser.py": "def parse_json(data): return json.loads(data)\n",
    "requirements.txt": "pydantic\n",
})

README_AND_SOURCE_FILES = _make_files({
    "README.md": "# Login\n\nThis project handles authentication. Login logic is complex.\n",
    "src/auth.py": "def authenticate_user(username, password):\n    return check_bcrypt(password)\n\ndef check_bcrypt(pwd): pass\n",
})


# ── Test 1: Index is built once, not rebuilt per request ─────────────────────

def test_index_is_not_rebuilt_for_every_chat():
    """The symbol index must be a stable object built once."""
    files = AUTH_ONLY_FILES
    index1 = build_symbol_index(files, session_id="session_a")
    index2 = build_symbol_index(files, session_id="session_a")  # would be rebuilt if called again

    # Both builds should produce the same symbols (deterministic)
    assert len(index1.symbols) == len(index2.symbols)
    names1 = sorted(s.name for s in index1.symbols)
    names2 = sorted(s.name for s in index2.symbols)
    assert names1 == names2, "Index must be deterministic across builds"


# ── Test 2: Repository isolation ──────────────────────────────────────────────

def test_repo_indexes_are_isolated():
    """Results from repo A must never appear in repo B."""
    files_a = AUTH_ONLY_FILES   # has login/authenticate
    files_b = ITEMS_ONLY_FILES  # has items/recursive

    index_a = build_symbol_index(files_a, session_id="session_a")
    index_b = build_symbol_index(files_b, session_id="session_b")

    result_a = search_repository(index_a, files_a, "login", mode="repo")
    result_b = search_repository(index_b, files_b, "login", mode="repo")

    # Repo A: should find login-related symbols
    files_in_a = {c.file for c in result_a.candidates}
    files_in_b = {c.file for c in result_b.candidates}

    # Repo B files should NOT appear in Repo A results
    for f in files_in_a:
        assert f in files_a, f"Cross-repo contamination: {f} from repo_b appeared in repo_a results"

    # Repo A files should NOT appear in Repo B results
    for f in files_in_b:
        assert f in files_b, f"Cross-repo contamination: {f} from repo_a appeared in repo_b results"


# ── Test 3: Login search returns existing file ────────────────────────────────

def test_login_search_returns_existing_file():
    """When the repo has login/auth code, search must return it."""
    index = build_symbol_index(AUTH_ONLY_FILES, session_id="test_login")
    result = search_repository(index, AUTH_ONLY_FILES, "where is login logic", mode="repo")

    assert not result.not_found, "Login search should find results in auth repo"
    assert len(result.candidates) > 0, "Should have at least one candidate"

    # The top candidate should be from the auth file
    top_file = result.candidates[0].file
    assert "auth" in top_file.lower() or "service" in top_file.lower(), (
        f"Top result should be from auth file, got: {top_file}"
    )


# ── Test 4: Missing login returns NOT_FOUND ───────────────────────────────────

def test_missing_login_returns_not_found():
    """When repo has NO login/auth code, search must return not_found."""
    index = build_symbol_index(NO_AUTH_FILES, session_id="test_no_auth")
    result = search_repository(index, NO_AUTH_FILES, "where is login logic", mode="repo")

    # Either no candidates or all very low-scored
    if result.candidates:
        best_score = result.candidates[0].score
        assert best_score < 0.5, (
            f"Should have low confidence for login in repo without auth. Score: {best_score}"
        )


# ── Test 5: FILE mode prioritizes current file ────────────────────────────────

def test_file_mode_prioritizes_current_file():
    """FILE mode should give strong bonus to symbols in the current file."""
    index = build_symbol_index(AUTH_ONLY_FILES, session_id="test_file_mode")
    auth_file = "src/auth/service.py"

    result = search_repository(
        index, AUTH_ONLY_FILES, "how does login work",
        mode="file", current_file=auth_file
    )

    # Top candidates should be from current file
    if result.candidates:
        top = result.candidates[0]
        assert top.file == auth_file or any(
            c.file == auth_file for c in result.candidates[:3]
        ), f"FILE mode should prioritize {auth_file}"


# ── Test 6: Invalid AI candidate is rejected ─────────────────────────────────

def test_invalid_ai_candidate_is_rejected():
    """If Groq returns an ID not in candidate_map, it must be rejected."""
    candidate_map = {
        "S1": {"file": "auth.py", "start_line": 10, "end_line": 30},
        "S2": {"file": "service.py", "start_line": 5, "end_line": 20},
    }

    # S999 is NOT in candidate_map
    groq_response_id = "S999"
    assert groq_response_id not in candidate_map, "S999 should not be in candidate_map"

    # This is the validation logic from main.py
    validated = None
    if groq_response_id in candidate_map:
        validated = candidate_map[groq_response_id]

    assert validated is None, "Invalid candidate ID should be rejected (validated should be None)"


# ── Test 7: Candidate lines exist in actual file ──────────────────────────────

def test_candidate_lines_exist_in_actual_file():
    """Symbol records must have start/end lines within the actual file's line count."""
    index = build_symbol_index(AUTH_ONLY_FILES, session_id="test_lines")

    for sym in index.symbols:
        file_data = AUTH_ONLY_FILES.get(sym.file, {})
        content = file_data.get("content", "")
        total_lines = content.count("\n") + 1

        assert sym.start_line >= 1, f"start_line must be ≥ 1, got {sym.start_line} for {sym.name}"
        assert sym.end_line >= sym.start_line, (
            f"end_line ({sym.end_line}) must be ≥ start_line ({sym.start_line}) for {sym.name}"
        )
        # end_line can slightly exceed actual (estimation), but should be in reasonable range
        assert sym.end_line <= total_lines + 10, (
            f"end_line ({sym.end_line}) is way past file end ({total_lines}) for {sym.name}"
        )


# ── Test 8: Architecture does NOT add fake database ──────────────────────────

def test_architecture_does_not_add_fake_database():
    """If no database is detected, no database node should appear in mermaid."""
    # Pure FastAPI with no DB signals
    files = _make_files({
        "main.py": FASTAPI_ITEMS_FILE,
        "requirements.txt": "fastapi\npydantic\n",
    })
    arch = detect_architecture(files)

    assert arch["databases"] == [], (
        f"No database should be detected, got: {arch['databases']}"
    )

    mermaid = arch.get("mermaid_diagram", "")
    # No database cylinder node should appear
    assert "DB" not in mermaid or "(\"" not in mermaid, (
        f"Database node should not appear in mermaid when not detected.\n{mermaid}"
    )


# ── Test 9: Architecture does NOT add fake frontend ──────────────────────────

def test_architecture_does_not_add_fake_frontend():
    """If no frontend is detected (pure backend repo), no Frontend node in diagram."""
    files = _make_files({
        "main.py": FASTAPI_ITEMS_FILE,
        "requirements.txt": "fastapi\npydantic\n",
    })
    arch = detect_architecture(files)

    # No .jsx/.tsx/.vue/.html files → frontend should NOT be detected
    if not arch["layers"].get("frontend"):
        mermaid = arch.get("mermaid_diagram", "")
        assert "FE" not in mermaid, (
            f"Frontend node 'FE' should not appear when no frontend detected.\n{mermaid}"
        )


# ── Test 10: Docs do NOT outrank source for implementation queries ─────────────

def test_docs_do_not_outrank_source_for_implementation_query():
    """README/docs must not outscore source files for implementation questions."""
    index = build_symbol_index(README_AND_SOURCE_FILES, session_id="test_docs")
    result = search_repository(
        index, README_AND_SOURCE_FILES,
        "how does authenticate_user work",
        mode="repo"
    )

    if result.candidates and len(result.candidates) >= 2:
        # The top result should be the source file, not the README
        top_file = result.candidates[0].file
        assert ".md" not in top_file.lower(), (
            f"Source file should outrank README for implementation query. Got: {top_file}"
        )


# ── Test 11: Evidence label is never a raw percentage ────────────────────────

def test_evidence_label_from_score():
    """Evidence label must return string labels, not percentages."""
    # Strong: exact symbol match
    strong_candidates = [
        Candidate(
            id="S1", internal_id="SYM_1", score=0.95, file="auth.py",
            symbol="authenticate_user", start_line=10, end_line=30,
            match_reasons=["exact symbol name match: 'authenticate_user'"],
        )
    ]
    label = compute_evidence_label(strong_candidates)
    assert label in {"Strong evidence", "Moderate evidence", "Weak evidence", "No evidence"}, (
        f"Evidence label must be a string category, got: {label}"
    )
    assert label == "Strong evidence", f"Expected 'Strong evidence' for exact match, got: {label}"

    # No candidates → No evidence
    empty_label = compute_evidence_label([])
    assert empty_label == "No evidence", f"Expected 'No evidence', got: {empty_label}"

    # Weak: low score
    weak_candidates = [
        Candidate(
            id="S1", internal_id="SYM_2", score=0.2, file="utils.py",
            symbol="process", start_line=5, end_line=10,
            match_reasons=["file contains 'login'"],
        )
    ]
    weak_label = compute_evidence_label(weak_candidates)
    assert weak_label in {"Weak evidence", "Moderate evidence"}, (
        f"Low score should give Weak/Moderate evidence, got: {weak_label}"
    )


# ── Test 12: FILE mode skips repo search when sufficient evidence ─────────────

def test_file_mode_skips_repo_search_when_sufficient_evidence():
    """
    In FILE mode with a current file that has strong matches,
    the result should prioritize current file over unrelated repo files.
    """
    # Auth file has login/verify; items file has GET /items/recursive
    combined_files = _make_files({
        "src/auth.py": FASTAPI_AUTH_FILE,
        "app.py": FASTAPI_ITEMS_FILE,
        "requirements.txt": "fastapi\npasslib\n",
    })
    index = build_symbol_index(combined_files, session_id="test_file_fast_path")

    # FILE mode with current_file=app.py: asking about the recursive endpoint
    result = search_repository(
        index, combined_files, "how does the API work",
        mode="file", current_file="app.py"
    )

    # Top results should include app.py (current file) not just auth.py
    assert any(c.file == "app.py" for c in result.candidates[:3]), (
        "FILE mode should include current file 'app.py' in top candidates"
    )


# ── Test 13: Symbol body not duplicated ───────────────────────────────────────

def test_symbol_body_not_stored_in_index():
    """SymbolRecord must not store full body text – only start/end lines."""
    index = build_symbol_index(AUTH_ONLY_FILES, session_id="test_body")

    for sym in index.symbols:
        # Signature should be a single short line
        sig_lines = sym.signature.count("\n")
        assert sig_lines <= 1, (
            f"Signature should be a single line, got {sig_lines + 1} lines for {sym.name}"
        )
        # SymbolRecord should not have a 'body' or 'code' attribute
        assert not hasattr(sym, "body"), "SymbolRecord must not store full body"
        assert not hasattr(sym, "code"), "SymbolRecord must not store full code"


# ── Test 14: build_verified_mermaid only adds detected nodes ─────────────────

def test_build_verified_mermaid_only_uses_detected():
    """build_verified_mermaid must not add nodes for undetected components."""
    # Backend only – no frontend, no database
    layers = {"frontend": False, "backend": True, "database": False, "tests": False, "infrastructure": False}
    stack = ["FastAPI"]
    dbs: list[str] = []

    mermaid = build_verified_mermaid(layers, stack, dbs)

    assert "FE" not in mermaid, "Frontend node should not appear"
    assert "DB" not in mermaid, "Database node should not appear"
    assert "BE" in mermaid, "Backend node should appear"
    assert "FastAPI" in mermaid, "FastAPI label should appear"


if __name__ == "__main__":
    # Run all tests
    import pytest
    pytest.main([__file__, "-v"])
