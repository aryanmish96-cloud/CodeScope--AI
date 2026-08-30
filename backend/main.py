"""
main.py – FastAPI application entry point for CodeScope AI backend.

KEY CHANGES (grounded intelligence refactor):
- _repo_indexes[session_id]: symbol index built ONCE during analysis, reused for all /chat calls.
- /chat endpoint: local search → real candidates → Groq selects ID → backend validates → resolve.
- /analyze-architecture: uses verified mermaid from architecture.py; Groq only writes explanation.
- NOT_FOUND: returns a grounded "insufficient evidence" message instead of hallucinating.
- candidate_map validation: any Groq-invented ID that's not in candidate_map is rejected.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# Ensure .env is loaded from the backend directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from repo_parser import parse_repository, RepoTooLargeError
from repo_indexer import build_symbol_index, RepoIndex
from repo_search import search_repository, compute_evidence_label
from graph_builder import build_graph
from architecture import detect_architecture, build_verified_mermaid
from ai_engine import (
    generate_readme,
    scan_security_risks,
    analyze_architecture as ai_analyze_architecture,
    simulate_execution,
    summarize_repo,
    explain_file,
    chat_with_repo,
)

logger = logging.getLogger("codescope")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CodeScope AI API",
    description="Intelligent Codebase Explorer & Explainer",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error Handlers ─────────────────────────────────────────────────────────────
@app.exception_handler(RepoTooLargeError)
async def repo_too_large_handler(request: Request, exc: RepoTooLargeError):
    return JSONResponse(
        status_code=413,
        content={"detail": str(exc)},
    )

# All JSON API routes live under /api
api = APIRouter(prefix="/api", tags=["codescope"])

# ── In-memory session store ────────────────────────────────────────────────────
# Maps session_id → full analysis payload
_sessions: dict[str, dict[str, Any]] = {}

# Maps session_id → RepoIndex (built ONCE per session during analysis pipeline)
# NEVER rebuilt inside /chat request handlers.
_repo_indexes: dict[str, RepoIndex] = {}

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_analysis_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="codescope-analysis")


# ── Request / Response Models ──────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., min_length=1, description="HTTPS GitHub repository URL")
    session_id: str | None = None

    @field_validator("repo_url")
    @classmethod
    def repo_url_nonempty(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("repo_url cannot be empty")
        return s

class AnalyzeStartResponse(BaseModel):
    job_id: str


class AnalyzeStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str | None = None
    error: str | None = None
    started_at: float
    updated_at: float


def _new_session_id(repo_url: str) -> str:
    return hashlib.md5(f"{repo_url}{time.time()}".encode()).hexdigest()[:12]


def _new_job_id(repo_url: str) -> str:
    return hashlib.md5(f"job:{repo_url}:{time.time()}".encode()).hexdigest()[:16]


def _run_analysis_pipeline(repo_url: str, set_status=None) -> dict[str, Any]:
    parsed = parse_repository(repo_url, update_status=set_status)
    files = parsed["files"]
    imports = parsed["imports"]
    stats = parsed["stats"]
    tree = parsed["tree"]
    git_meta = parsed.get("git", {})

    if set_status:
        set_status("Building dependency graph...")
    graph = build_graph(files, imports, update_status=set_status)

    if set_status:
        set_status("Detecting architecture...")
    arch = detect_architecture(files)

    if set_status:
        set_status("Running security scan...")
    risks = scan_security_risks(files)

    session_id = _new_session_id(repo_url)

    # ── Build symbol index ONCE (not per-request) ──────────────────────────────
    if set_status:
        set_status("Building symbol index...")
    try:
        repo_index = build_symbol_index(files, session_id=session_id)
        _repo_indexes[session_id] = repo_index
        logger.info(
            "Symbol index built for session %s: %d symbols, %d keyword entries",
            session_id,
            len(repo_index.symbols),
            len(repo_index.keyword_index),
        )
    except Exception as e:
        logger.warning("Symbol index build failed (chat will use file-level fallback): %s", e)
        _repo_indexes[session_id] = None  # type: ignore[assignment]

    _sessions[session_id] = {
        "repo_url": repo_url,
        "repo_name": stats["repo_name"],
        "files": files,
        "imports": imports,
        "stats": stats,
        "arch": arch,
        "graph": graph,
        "git": git_meta,
    }

    return {
        "session_id": session_id,
        "repo_name": stats["repo_name"],
        "tree": tree,
        "graph": graph,
        "architecture": arch,
        "stats": {**stats, "git": git_meta},
        "security_risks": risks,
    }


def _start_analysis_job(repo_url: str) -> str:
    job_id = _new_job_id(repo_url)
    now = time.time()
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "repo_url": repo_url,
            "status": "queued",
            "message": "Queued for analysis...",
            "error": None,
            "result": None,
            "started_at": now,
            "updated_at": now,
        }

    def update_status(message: str):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job["message"] = message
            job["updated_at"] = time.time()
            if job["status"] in {"queued", "running"}:
                job["status"] = "running"

    def worker():
        update_status("Starting analysis...")
        try:
            result = _run_analysis_pipeline(repo_url, set_status=update_status)
            with _jobs_lock:
                job = _jobs.get(job_id)
                if not job:
                    return
                job["status"] = "done"
                job["message"] = "Analysis complete."
                job["result"] = result
                job["updated_at"] = time.time()
        except Exception as exc:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if not job:
                    return
                job["status"] = "error"
                job["error"] = str(exc)
                job["message"] = "Analysis failed."
                job["updated_at"] = time.time()
            logger.exception("Analysis job failed: %s", job_id)

    _analysis_pool.submit(worker)
    return job_id


class SummarizeRequest(BaseModel):
    session_id: str = Field(..., min_length=1)

    @field_validator("session_id")
    @classmethod
    def session_id_nonempty(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("session_id is required")
        return s


class FileExplainRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    eli5: bool = False

    @field_validator("session_id", "file_path")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("field cannot be empty")
        return s


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    history: list[dict] = Field(default_factory=list)
    # Grounded chat fields (optional – backward compatible with old frontend)
    current_file: str | None = None    # Currently open file path
    mode: str = "repo"                 # "file" | "flow" | "repo"

    @field_validator("session_id", "question")
    @classmethod
    def chat_strip(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("field cannot be empty")
        return s

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = (v or "repo").lower().strip()
        if v not in {"file", "flow", "repo"}:
            return "repo"
        return v


class ReadmeRequest(BaseModel):
    session_id: str = Field(..., min_length=1)

    @field_validator("session_id")
    @classmethod
    def readme_session(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("session_id is required")
        return s


# ── Health check ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "model": "openai/gpt-oss-120b", "provider": "groq"}


# ── Analyze repository ────────────────────────────────────────────────────────────
@api.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Clone and fully analyze a GitHub repository.
    Returns: file tree, dependency graph, architecture, stats, security risks.
    Also builds symbol index (stored per session for grounded chat).
    """
    repo_url = req.repo_url
    if not repo_url.startswith("http"):
        raise HTTPException(400, "Invalid repository URL — must start with http:// or https://")

    logger.info("POST /api/analyze repo_url=%s", repo_url[:120])

    try:
        return _run_analysis_pipeline(repo_url)
    except RepoTooLargeError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@api.post("/analyze/start", response_model=AnalyzeStartResponse)
def analyze_start(req: AnalyzeRequest):
    repo_url = req.repo_url
    if not repo_url.startswith("http"):
        raise HTTPException(400, "Invalid repository URL — must start with http:// or https://")
    logger.info("POST /api/analyze/start repo_url=%s", repo_url[:120])
    job_id = _start_analysis_job(repo_url)
    return {"job_id": job_id}


@api.get("/analyze/status/{job_id}", response_model=AnalyzeStatusResponse)
def analyze_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Analysis job not found.")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "message": job.get("message"),
            "error": job.get("error"),
            "started_at": job["started_at"],
            "updated_at": job["updated_at"],
        }


@api.get("/analyze/result/{job_id}")
def analyze_result(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Analysis job not found.")
        status = job["status"]
        if status in {"queued", "running"}:
            raise HTTPException(202, "Analysis still in progress.")
        if status == "error":
            raise HTTPException(500, f"Analysis failed: {job.get('error') or 'Unknown error'}")
        result = job.get("result")
        if result is None:
            raise HTTPException(500, "Analysis result missing.")
        return result


# ── AI Repo Summary ──────────────────────────────────────────────────────────────
@api.post("/summarize")
def summarize(req: SummarizeRequest):
    """Get AI-powered repo summary (call after /api/analyze)."""
    logger.info("POST /api/summarize session_id=%s", req.session_id)
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(
            404,
            "Session not found. Run /api/analyze again (sessions are in-memory and reset if the server restarts).",
        )

    files = session["files"]
    arch = session["arch"]
    graph = session["graph"]

    important_paths = [f["path"] for f in graph["metrics"]["important_files"]]
    sample_contents = {p: files[p]["content"] for p in important_paths if p in files}

    try:
        result = summarize_repo(
            repo_url=session.get("repo_url", "Unknown"),
            repo_name=session["repo_name"],
            tech_stack=arch["tech_stack"],
            file_count=session["stats"]["file_count"],
            total_lines=session["stats"]["total_lines"],
            important_files=graph["metrics"]["important_files"],
            project_type=arch["project_type"],
            sample_contents=sample_contents,
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Summarization failed: {str(e)}")


# ── File Explanation ──────────────────────────────────────────────────────────────
@api.post("/explain-file")
def explain_file_endpoint(req: FileExplainRequest):
    """Get AI explanation for a specific file."""
    logger.info("POST /api/explain-file session_id=%s path=%s", req.session_id, req.file_path)
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Run /api/analyze again.")

    file_data = session["files"].get(req.file_path)
    if not file_data:
        raise HTTPException(404, f"File not found: {req.file_path}")

    content = file_data.get("content", "")
    if not content.strip():
        return {
            "summary": "This file appears to be empty or binary.",
            "key_functions": [],
            "logic_flow": "",
            "role_in_project": "Unknown",
            "complexity_notes": "",
            "security_flags": [],
            "confidence": 0,
            "latency_ms": 0,
        }

    try:
        result = explain_file(
            path=req.file_path,
            content=content,
            eli5=req.eli5,
            tech_stack=session["arch"].get("tech_stack", []),
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Explanation failed: {str(e)}")


# ── Execution Simulation ────────────────────────────────────────────────────────
@api.post("/simulate-execution")
def simulate_execution_endpoint(req: FileExplainRequest):
    """Get AI-predicted execution flow for a specific file."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Run /api/analyze again.")

    file_data = session["files"].get(req.file_path)
    if not file_data:
        raise HTTPException(404, f"File not found: {req.file_path}")

    content = file_data.get("content", "")
    if not content.strip():
        return {
            "steps": [],
            "trigger": "Empty file",
            "data_objects": [],
            "confidence": 0,
            "latency_ms": 0,
        }

    try:
        result = simulate_execution(
            path=req.file_path,
            content=content,
            tech_stack=session["arch"].get("tech_stack", []),
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Simulation failed: {str(e)}")


def _not_found_response(question: str, query_expanded: list[str]) -> dict[str, Any]:
    """Return a NOT_FOUND response when evidence is insufficient."""
    return {
        "answer": (
            "I couldn't find enough repository evidence to answer this question confidently.\n\n"
            "Suggestions:\n"
            "• Try switching to **REPO** mode for broader search\n"
            "• Try rephrasing the question\n"
            "• Check if the feature exists in this repository\n"
            "• The feature may use different naming conventions"
        ),
        "relevant_files": [],
        "highlights": [],
        "reason": "Insufficient repository evidence",
        "evidence_label": "No evidence",
        "confidence": 0,
        "not_found": True,
        "query_terms": query_expanded[:10],
        "latency_ms": 0,
    }


# ── Chat ──────────────────────────────────────────────────────────────────────────
@api.post("/chat")
def chat(req: ChatRequest):
    """
    Grounded chat with the repository.

    Pipeline:
    1. Reuse cached symbol index (built during analysis – NEVER rebuilt here).
    2. Fast local search → ranked candidates with real code snippets + match_reasons.
    3. NOT_FOUND fast path if evidence is insufficient.
    4. ONE Groq call: receives real candidates, selects by ID.
    5. Backend validates returned candidate ID against candidate_map.
    6. Resolves validated ID to real file + lines.
    7. Returns highlights from verified data (not Groq invention).
    """
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Run /api/analyze again.")

    files = session["files"]

    # ── Get or lazily rebuild index (handles server restart) ──────────────────
    repo_index = _repo_indexes.get(req.session_id)
    if repo_index is None:
        logger.info("Lazily rebuilding symbol index for session %s", req.session_id)
        try:
            repo_index = build_symbol_index(files, session_id=req.session_id)
            _repo_indexes[req.session_id] = repo_index
        except Exception as e:
            logger.warning("Lazy index build failed: %s", e)
            repo_index = None

    # ── Fast local search (no Groq) ───────────────────────────────────────────
    t_search = time.time()
    search_result = None

    if repo_index is not None:
        try:
            search_result = search_repository(
                repo_index=repo_index,
                files=files,
                query=req.question,
                mode=req.mode,
                current_file=req.current_file,
                max_candidates=8,
                not_found_threshold=0.25,
            )
        except Exception as e:
            logger.warning("Search failed (will proceed with no candidates): %s", e)
            search_result = None

    search_ms = int((time.time() - t_search) * 1000)

    # NOT_FOUND fast path (if local search found nothing)
    if search_result is None or search_result.not_found or not search_result.candidates:
        logger.info(
            "NOT_FOUND for question='%s...' mode=%s current_file=%s",
            req.question[:60], req.mode, req.current_file,
        )
        resp = _not_found_response(req.question, search_result.query_expanded if search_result else [])
        resp["latency_ms"] = search_ms
        return resp

    # ── Build candidate_map (S1, S2, ...) for Groq and validation ─────────────
    candidate_map: dict[str, dict] = {}
    groq_candidates: list[dict] = []

    for i, c in enumerate(search_result.candidates):
        key = f"S{i + 1}"
        candidate_map[key] = {
            "file": c.file,
            "symbol": c.symbol,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "route_path": c.route_path,
            "sym_type": c.sym_type,
            "score": c.score,
            "match_reasons": c.match_reasons,
        }
        groq_candidates.append({
            "id": key,
            "file": c.file,
            "symbol": c.symbol,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "route_path": c.route_path,
            "sym_type": c.sym_type,
            "match_reasons": c.match_reasons,
            "snippet": c.snippet,
        })

    # Current file content for FILE mode
    current_file_content: str | None = None
    if req.current_file and req.mode == "file":
        fd = files.get(req.current_file, {})
        current_file_content = fd.get("content")

    # ── ONE Groq reasoning call ────────────────────────────────────────────────
    try:
        groq_result = chat_with_repo(
            question=req.question,
            candidates=groq_candidates,
            candidate_map=candidate_map,
            conversation_history=req.history,
            repo_context={
                "repo_name": session["repo_name"],
                "tech_stack": session["arch"].get("tech_stack", []),
            },
            current_file_content=current_file_content,
            mode=req.mode,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Chat failed: {str(e)}")

    # ── Backend validation: reject any candidate ID not in candidate_map ───────
    primary_id = groq_result.get("primary_candidate")
    related_ids = groq_result.get("related_candidates") or []

    # Validate primary
    validated_primary: dict | None = None
    if primary_id:
        if primary_id not in candidate_map:
            # Groq invented an ID – log and reject
            logger.warning(
                "Groq returned invalid candidate ID '%s' (not in candidate_map %s). Rejecting.",
                primary_id,
                list(candidate_map.keys()),
            )
            primary_id = None
        else:
            validated_primary = candidate_map[primary_id]

    # Validate related IDs
    validated_related: list[dict] = []
    for rid in related_ids[:4]:
        if rid in candidate_map:
            validated_related.append(candidate_map[rid])
        else:
            logger.warning("Groq returned invalid related candidate ID '%s'. Skipping.", rid)

    # If primary was rejected AND no valid related → NOT_FOUND
    if validated_primary is None and not validated_related:
        logger.info("All Groq-returned candidate IDs were invalid. Returning NOT_FOUND.")
        resp = _not_found_response(req.question, search_result.query_expanded)
        resp["latency_ms"] = groq_result.get("latency_ms", 0)
        return resp

    # ── Resolve validated candidates to real file + lines ─────────────────────
    highlights: list[dict] = []

    if validated_primary:
        highlights.append({
            "file": validated_primary["file"],
            "lines": [validated_primary["start_line"], validated_primary["end_line"]],
            "symbol": validated_primary.get("symbol"),
            "route": validated_primary.get("route_path"),
        })

    for rel in validated_related[:3]:
        highlights.append({
            "file": rel["file"],
            "lines": [rel["start_line"], rel["end_line"]],
            "symbol": rel.get("symbol"),
            "route": rel.get("route_path"),
        })

    # Build relevant_files list (de-duplicated)
    seen_files: set[str] = set()
    relevant_files: list[str] = []
    for h in highlights:
        if h["file"] not in seen_files:
            seen_files.add(h["file"])
            relevant_files.append(h["file"])

    # Compute evidence label from retrieved candidates
    evidence_label = compute_evidence_label(search_result.candidates)

    # Build evidence pills data for the UI
    evidence_pills: list[dict] = []
    if validated_primary:
        p = validated_primary
        sym_label = p.get("symbol") or p["file"].split("/")[-1]
        evidence_pills.append({
            "file": p["file"],
            "filename": p["file"].split("/")[-1],
            "start_line": p["start_line"],
            "end_line": p["end_line"],
            "symbol": sym_label,
            "route": p.get("route_path"),
            "reasons": candidate_map.get(primary_id, {}).get("match_reasons", []),
            "is_primary": True,
        })
    for i, rel in enumerate(validated_related[:3]):
        rid = related_ids[i] if i < len(related_ids) else None
        sym_label = rel.get("symbol") or rel["file"].split("/")[-1]
        evidence_pills.append({
            "file": rel["file"],
            "filename": rel["file"].split("/")[-1],
            "start_line": rel["start_line"],
            "end_line": rel["end_line"],
            "symbol": sym_label,
            "route": rel.get("route_path"),
            "reasons": candidate_map.get(rid, {}).get("match_reasons", []) if rid else [],
            "is_primary": False,
        })

    return {
        "answer": groq_result.get("answer", ""),
        "reasoning": groq_result.get("reasoning", ""),
        "relevant_files": relevant_files,
        "highlights": highlights,
        "evidence_pills": evidence_pills,
        "evidence_label": evidence_label,
        "reason": groq_result.get("reasoning", ""),
        "confidence": 0,   # deprecated – use evidence_label
        "not_found": False,
        "search_ms": search_ms,
        "latency_ms": groq_result.get("latency_ms", 0),
    }


# ── README Generator ──────────────────────────────────────────────────────────────
@api.post("/generate-readme")
def readme(req: ReadmeRequest):
    """Generate a professional README for the repository."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Run /api/analyze again.")

    arch = session["arch"]
    graph = session["graph"]

    summary_text = f"A {arch['project_type']} built with {', '.join(arch['tech_stack'][:3])}"

    try:
        result = generate_readme(
            repo_name=session["repo_name"],
            tech_stack=arch["tech_stack"],
            project_type=arch["project_type"],
            summary=summary_text,
            important_files=graph["metrics"]["important_files"],
            architecture_flow=arch.get("architecture_flow", []),
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"README generation failed: {str(e)}")


# ── AI Architecture Analysis (grounded) ──────────────────────────────────────────
@api.post("/analyze-architecture")
def arch_analysis(req: SummarizeRequest):
    """
    Get AI-powered deep architecture analysis.
    Mermaid diagram comes from detect_architecture() (verified, not Groq-generated).
    Groq only writes the text explanation based on detected components.
    """
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Run /api/analyze again.")

    arch = session["arch"]
    try:
        result = ai_analyze_architecture(
            repo_name=session["repo_name"],
            files=session["files"],
            tech_stack=arch["tech_stack"],
            project_type=arch["project_type"],
            detected_arch=arch,  # Pass verified arch to prevent hallucination
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Architecture analysis failed: {str(e)}")


# ── File content (raw) ────────────────────────────────────────────────────────────
@api.get("/file-content")
def file_content(session_id: str, file_path: str):
    """Get raw file content."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    file_data = session["files"].get(file_path)
    if not file_data:
        raise HTTPException(404, "File not found.")
    return {
        "path": file_path,
        "content": file_data.get("content", ""),
        "lines": file_data.get("lines", 0),
        "extension": file_data.get("extension", ""),
        "content_truncated": bool(file_data.get("content_truncated", False)),
        "size_bytes": int(file_data.get("size_bytes", 0)),
    }
# ── Graph Lazy-Loading APIs ───────────────────────────────────────────────────
@api.get("/graph/overview")
def get_graph_overview(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
        
    graph = session["graph"]
    # Overview returns repository and top-level modules
    nodes = [n for n in graph["nodes"] if n["type"] in ["repository", "module"] and (n["parent_id"] is None or n["parent_id"] == "repository:root")]
    
    # We only return edges between these returned nodes
    node_ids = set(n["id"] for n in nodes)
    edges = [e for e in graph["edges"] if e["source"] in node_ids and e["target"] in node_ids]
    
    return {"nodes": nodes, "edges": edges}

@api.get("/graph/nodes/{node_id:path}/children")
def get_graph_node_children(session_id: str, node_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
        
    graph = session["graph"]
    children = [n for n in graph["nodes"] if n["parent_id"] == node_id]
    
    # Edges where both source and target are in the returned set (or involving the parent)
    child_ids = set(n["id"] for n in children)
    child_ids.add(node_id)
    edges = [e for e in graph["edges"] if e["source"] in child_ids and e["target"] in child_ids]
    
    return {"nodes": children, "edges": edges}

@api.get("/graph/nodes/{node_id:path}/dependencies")
def get_graph_node_dependencies(session_id: str, node_id: str, hops: int = 1, direction: str = "both"):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
        
    graph = session["graph"]
    all_edges = graph["edges"]
    
    visited_nodes = {node_id}
    result_edges = []
    
    current_frontier = {node_id}
    
    for _ in range(hops):
        next_frontier = set()
        for edge in all_edges:
            if direction in ["both", "upstream"] and edge["target"] in current_frontier:
                next_frontier.add(edge["source"])
                result_edges.append(edge)
            if direction in ["both", "downstream"] and edge["source"] in current_frontier:
                next_frontier.add(edge["target"])
                result_edges.append(edge)
        
        current_frontier = next_frontier - visited_nodes
        visited_nodes.update(current_frontier)
        if not current_frontier:
            break
            
    # Include all nodes that are in the result edges
    result_node_ids = set()
    for e in result_edges:
        result_node_ids.add(e["source"])
        result_node_ids.add(e["target"])
    
    # Also include the queried node itself
    result_node_ids.add(node_id)
        
    result_nodes = [n for n in graph["nodes"] if n["id"] in result_node_ids]
    
    return {"nodes": result_nodes, "edges": result_edges}


app.include_router(api)


# ── Static files & SPA catch-all ───────────────────────────────────────────────
dist_path = os.getenv(
    "FRONTEND_DIST_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
)

logger.info(f"Looking for static files in: {dist_path}")

if os.path.exists(dist_path):
    logger.info("Static files directory found. Mounting /assets and SPA catch-all.")
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        local_file = os.path.join(dist_path, full_path)
        if os.path.isfile(local_file):
            return FileResponse(local_file)
        index_file = os.path.join(dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Static files not found")
else:
    logger.warning(f"Static files directory NOT found at: {dist_path}. SPA will not be served.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
