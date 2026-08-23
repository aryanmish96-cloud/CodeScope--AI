"""
ai_engine.py – Groq integration for CodeScope AI (model: openai/gpt-oss-120b).
Handles: file explanation, repo summary, ELI5, chat, README generation, risk radar.

GROUNDING RULES (chat_with_repo):
- Groq receives ONLY verified repository candidates from local search.
- Groq selects candidate IDs (S1, S2, ...) – never invents filenames/lines.
- Backend validates returned IDs against candidate_map before resolving to real locations.
- Temperature 0.1 for repository analysis tasks.
"""

from __future__ import annotations

import os
import re
import time
import json
from typing import Any

from groq import Groq

_client: Groq | None = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        _client = Groq(api_key=api_key)
    return _client

MODEL_NAME = "openai/gpt-oss-120b"

# ── Grounded System Prompt ────────────────────────────────────────────────────
_GROUNDED_SYSTEM_PROMPT = """\
You are CodeScope AI, a repository-grounded code intelligence assistant.

You are given VERIFIED repository evidence retrieved by CodeScope's local search engine.
All candidates below were found by deterministic parsing of the actual repository source code.
You MUST NOT invent, assume, or fabricate any repository facts.

RULES:
1. Base all repository-specific claims on the supplied candidates only.
2. Never invent filenames, directory paths, function names, class names, routes, or line numbers.
3. Reference only the candidate IDs (S1, S2, ...) supplied in the user message.
4. If evidence is insufficient, return {"found": false, "reason": "..."}.
5. Never assume a database, frontend, authentication system, service, or API exists unless evidence shows it.
6. Accuracy is more important than answering every question.
7. Separate verified facts from your interpretation.
8. Never fabricate code.
9. If the question can be answered from FILE mode (current file provided), prefer that over speculation.
"""

# ── Evidence label ──────────────────────────────────────────────────────────
def _evidence_label(score: float, match_count: int, has_exact: bool) -> str:
    """Return human-readable evidence label. Never returns a raw percentage."""
    if has_exact or (score >= 0.8 and match_count >= 2):
        return "Strong evidence"
    if score >= 0.5 or match_count >= 1:
        return "Moderate evidence"
    return "Weak evidence"


# ── file explanation ────────────────────────────────────────────────────────
def explain_file(
    path: str,
    content: str,
    *,
    eli5: bool = False,
    tech_stack: list[str] | None = None,
) -> dict[str, Any]:
    client = _get_client()
    tech_hint = f"Tech stack context: {', '.join(tech_stack)}." if tech_stack else ""

    if eli5:
        style = "Explain this code like I'm 10 years old. Use simple words, fun analogies, and avoid jargon."
    else:
        style = "Explain this code clearly to a senior developer. Be concise and precise. Reference actual functions and patterns from the code."

    system = "You are a helpful assistant that outputs JSON. Reference only the actual code provided."
    prompt = f"""{style}

File: {path}
{tech_hint}

```
{content[:8000]}
```

Respond with a JSON object with these exact keys:
 {{
   "summary": "2-3 sentence overview of what THIS specific file does (not a generic framework explanation)",
   "key_functions": [
     {{ "name": "functionName", "description": "concise description of what this specific function does" }}
   ],
   "logic_flow": "step-by-step description of the main logic flow in this file",
   "role_in_project": "what role does this file play in the overall project",
   "complexity_notes": "notable complexity, patterns, or anti-patterns in THIS file",
   "security_flags": ["any potential security issues found, empty list if none"]
 }}
"""
    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1536,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"Groq Explain Error: {e}")
        data = {"summary": f"Failed to analyze code: {str(e)}", "key_functions": [], "logic_flow": "", "role_in_project": "", "complexity_notes": "", "security_flags": []}

    elapsed = time.time() - t0
    data["confidence"] = 80 if data.get("summary") else 30
    data["latency_ms"] = int(elapsed * 1000)
    return data

# ── repo 60-second summary ────────────────────────────────────────────────────────
def summarize_repo(
    repo_url: str,
    repo_name: str,
    tech_stack: list[str],
    file_count: int,
    total_lines: int,
    important_files: list[dict],
    project_type: str,
    sample_contents: dict[str, str],
) -> dict[str, Any]:
    client = _get_client()

    samples_text = ""
    for path, content in list(sample_contents.items())[:4]:
        samples_text += f"\n### {path}\n```\n{content[:1500]}\n```\n"

    system = "You are a helpful assistant that outputs JSON. Base your analysis on the provided file contents."
    prompt = f"""You are analyzing the GitHub repository: {repo_name}
URL: {repo_url}

Project type: {project_type}
Tech stack: {', '.join(tech_stack) or 'Unknown'}
Files: {file_count} | Total lines: {total_lines:,}
Most important files: {', '.join(f['path'] for f in important_files[:5])}

Sample file contents:{samples_text}

Provide a comprehensive repository analysis as JSON:
{{
  "elevator_pitch": "One punchy sentence describing what this repo does based on the actual code",
  "detailed_summary": "3-4 sentence summary of the project purpose, architecture, and usage based on the files above",
  "sixty_second_explanation": "A 60-second verbal explanation a developer could give to a non-technical stakeholder",
  "strengths": ["list of 3-5 architectural or code strengths visible in the code"],
  "weaknesses": ["list of 2-3 potential issues or areas for improvement"],
  "use_cases": ["2-3 real-world use cases for this project"],
  "getting_started": "One paragraph on how to get started with this codebase",
  "complexity_assessment": "low | medium | high",
  "maintainability_score": 0-10
}}"""

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1536,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"Groq Summarize Error: {e}")
        data = {"elevator_pitch": f"Failed to analyze repo logic: {str(e)}", "detailed_summary": "", "sixty_second_explanation": ""}

    elapsed = time.time() - t0
    data["confidence"] = 80
    data["latency_ms"] = int(elapsed * 1000)
    return data

# ── Grounded chat with repo ────────────────────────────────────────────────────────
def chat_with_repo(
    question: str,
    candidates: list[dict],         # Pre-retrieved real candidates [{id, file, symbol, snippet, match_reasons, ...}]
    candidate_map: dict[str, dict],  # id → candidate dict (for reference)
    conversation_history: list[dict],
    repo_context: dict,
    current_file_content: str | None = None,
    mode: str = "repo",
) -> dict[str, Any]:
    """
    Groq-powered chat grounded in real repository evidence.

    This function assumes candidates were already retrieved by repo_search.search_repository().
    Groq receives only the supplied candidates and must select from them by ID.
    It must NOT invent file paths, line numbers, or symbol names.

    Temperature is set to 0.1 for repository analysis (not creative mode).
    """
    client = _get_client()

    # Build context block from real candidates
    candidates_block = ""
    for c in candidates:
        cid = c.get("id", "?")
        file_path = c.get("file", "?")
        symbol = c.get("symbol") or "(file level)"
        sym_type = c.get("sym_type", "")
        start_ln = c.get("start_line", 1)
        end_ln = c.get("end_line", 1)
        route = c.get("route_path")
        reasons = c.get("match_reasons", [])
        snippet = c.get("snippet", "")

        candidates_block += f"\n---\nCandidate {cid}:\n"
        candidates_block += f"File: {file_path}\n"
        candidates_block += f"Symbol: {symbol} ({sym_type})\n"
        candidates_block += f"Lines: {start_ln}–{end_ln}\n"
        if route:
            candidates_block += f"Route: {route}\n"
        if reasons:
            candidates_block += f"Match reasons: {'; '.join(reasons[:3])}\n"
        if snippet:
            candidates_block += f"Code:\n```\n{snippet[:1000]}\n```\n"

    # Current file context for FILE mode
    file_ctx = ""
    if current_file_content and mode == "file":
        file_ctx = f"\n\nCurrently open file content (primary context):\n```\n{current_file_content[:3000]}\n```\n"

    system = _GROUNDED_SYSTEM_PROMPT

    user_prompt = f"""Repository: {repo_context.get('repo_name', 'Unknown')}
Tech stack: {', '.join(repo_context.get('tech_stack', []))}
Mode: {mode.upper()}
{file_ctx}
Question: {question}

Repository evidence (verified by local search):
{candidates_block if candidates_block else "(No candidates found – insufficient evidence)"}

Respond with STRICT JSON only:
{{
  "found": true | false,
  "primary_candidate": "S1",
  "related_candidates": ["S2", "S3"],
  "answer": "Clear, specific explanation referencing the actual code in the candidates",
  "reasoning": "Brief explanation of why primary_candidate is the best match"
}}

RULES:
- "primary_candidate" and "related_candidates" MUST only reference IDs from the candidates above (S1, S2, ...).
- If no candidate is relevant, set "found": false and explain why.
- Do NOT invent any file path, line number, function name, or route not shown above.
- For FILE mode: base your answer primarily on the currently open file content if provided.
"""

    messages = [{"role": "system", "content": system}]

    for turn in conversation_history[-6:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        content = turn.get("content")
        if not content:
            continue
        messages.append({"role": role, "content": str(content)})

    messages.append({"role": "user", "content": user_prompt})

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=1024,
            temperature=0.1,  # Low temperature for deterministic repository reasoning
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"Groq Chat Error: {e}")
        data = {
            "found": False,
            "primary_candidate": None,
            "related_candidates": [],
            "answer": f"Error communicating with AI: {str(e)}",
            "reasoning": "",
        }

    elapsed = time.time() - t0
    data["latency_ms"] = int(elapsed * 1000)
    return data


# ── README generator ──────────────────────────────────────────────────────────────
def generate_readme(
    repo_name: str,
    tech_stack: list[str],
    project_type: str,
    summary: str,
    important_files: list[dict],
    architecture_flow: list[dict],
) -> dict[str, Any]:
    client = _get_client()

    flow_str = " → ".join(s["label"] for s in architecture_flow)

    prompt = f"""Generate a professional, impressive GitHub README.md for this project:

Repository: {repo_name}
Type: {project_type}
Stack: {', '.join(tech_stack)}
Summary: {summary}
Architecture: {flow_str}
Key files: {', '.join(f['path'] for f in important_files[:5])}

Include:
- Eye-catching header with badges
- Clear project description
- Feature list with emojis
- Installation instructions (generic based on detected stack)
- Usage examples
- Architecture section
- Contributing section
- License section

Make it look like a top GitHub project. Use proper markdown formatting."""

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1536,
        )
        readme = response.choices[0].message.content or ""
    except Exception as e:
        readme = f"# Error generating README\n{str(e)}"
    elapsed = time.time() - t0

    return {
        "readme": readme,
        "latency_ms": int(elapsed * 1000),
    }


# ── Execution Simulator ────────────────────────────────────────────────────────
def simulate_execution(
    path: str,
    content: str,
    tech_stack: list[str] | None = None,
) -> dict[str, Any]:
    """
    AI-predicted execution flow simulator.
    Returns a sequence of steps showing how this code would typically run.
    """
    client = _get_client()
    tech_hint = f"Tech stack: {', '.join(tech_stack)}." if tech_stack else ""

    system = "You are a senior systems architect. You output JSON only. Base your analysis on the provided code."
    prompt = f"""Predict the step-by-step execution flow of this file: {path}
{tech_hint}

```
{content[:8000]}
```

Provide a high-fidelity sequence of logical steps of how this code executes (at runtime).
Focus on: triggers, data flow, validations, transformations, and final outputs.
Reference actual function names and patterns from the code.

Return output in STRICT JSON format:
{{
  "steps": [
    {{ "id": 1, "label": "Short Action (3-5 words)", "description": "Detailed explanation referencing actual code", "icon": "emoji" }},
    ...
  ],
  "trigger": "What triggers this file (e.g., HTTP Request, Cron, Import)",
  "data_objects": ["main data objects involved"]
}}

IMPORTANT:
* Maximum 6-8 steps
* Icons should be tech-relevant emojis
* Make descriptions reference actual functions/patterns from the code
"""

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=1536,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"Groq Simulation Error: {e}")
        data = {
            "steps": [{"id": 1, "label": "Analysis Failed", "description": str(e), "icon": "❌"}],
            "trigger": "Error",
            "data_objects": []
        }

    elapsed = time.time() - t0
    data["latency_ms"] = int(elapsed * 1000)
    data["confidence"] = 80 if data.get("steps") else 30
    return data


# ── AI Architecture Analysis (grounded) ─────────────────────────────────────────
def analyze_architecture(
    repo_name: str,
    files: dict[str, dict],
    tech_stack: list[str],
    project_type: str,
    detected_arch: dict | None = None,
) -> dict[str, Any]:
    """
    AI-powered architecture analysis grounded in detected evidence.

    The mermaid diagram is generated from detect_architecture() output (verified).
    Groq only writes the text explanation based on detected components.
    No phantom Frontend/Database nodes.
    """
    client = _get_client()

    # Use already-detected architecture if provided
    if detected_arch:
        verified_layers = detected_arch.get("layers", {})
        verified_dbs = detected_arch.get("databases", [])
        verified_mermaid = detected_arch.get("mermaid_diagram", "")
        layer_evidence = detected_arch.get("layer_evidence", {})
        db_evidence = detected_arch.get("db_evidence", {})
    else:
        # Minimal fallback summary without Groq
        verified_layers = {}
        verified_dbs = []
        verified_mermaid = "graph TD\n  REPO[\"Repository\"]"
        layer_evidence = {}
        db_evidence = {}

    # Build a concise evidence summary to ground Groq's explanation
    evidence_summary = f"Repository: {repo_name}\n"
    evidence_summary += f"Project type: {project_type}\n"
    evidence_summary += f"Tech stack: {', '.join(tech_stack) or 'Unknown'}\n"
    evidence_summary += f"Detected databases: {', '.join(verified_dbs) or 'None'}\n"
    evidence_summary += f"Frontend detected: {verified_layers.get('frontend', False)}\n"
    evidence_summary += f"Backend detected: {verified_layers.get('backend', False)}\n"
    evidence_summary += f"Tests detected: {verified_layers.get('tests', False)}\n"
    evidence_summary += f"Infrastructure detected: {verified_layers.get('infrastructure', False)}\n"

    # Show a sample of key files (no large snippets – just paths)
    key_paths = list(files.keys())[:50]
    evidence_summary += f"\nKey file paths (sample):\n" + "\n".join(key_paths[:30])

    system = "You are an expert software architect. Output JSON only. Describe only what the evidence supports."
    prompt = f"""Based on the following VERIFIED repository evidence, provide an architecture explanation.

{evidence_summary}

RULES:
- Describe only what the evidence above confirms.
- Do NOT add components not listed (e.g., do not add "Database" if databases = None).
- Do NOT mention generic framework features as if they are in this repo.
- If a component is "Not detected", say so.

Return STRICT JSON:
{{
  "frontend": "React frontend" or "Not detected",
  "backend": "FastAPI backend" or "Not detected",
  "database": "PostgreSQL" or "Not detected",
  "apis": ["list of detected API route patterns or empty"],
  "explanation": "2-3 sentence description of THIS repository's architecture based only on the evidence above"
}}
"""

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=768,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"Groq Architecture Error: {e}")
        data = {
            "frontend": "Analysis failed",
            "backend": "Analysis failed",
            "database": "Not detected",
            "apis": [],
            "explanation": f"Error: {str(e)}"
        }

    elapsed = time.time() - t0

    # ALWAYS use the verified mermaid diagram from architecture.py (not from Groq)
    data["mermaid_diagram"] = verified_mermaid

    # Attach evidence from local detection
    data["layer_evidence"] = layer_evidence
    data["db_evidence"] = db_evidence
    data["tech_stack"] = tech_stack

    data["confidence"] = 80 if data.get("explanation") else 30
    data["latency_ms"] = int(elapsed * 1000)
    return data

# ── risk radar ────────────────────────────────────────────────────────────────────
def scan_security_risks(files: dict[str, dict]) -> list[dict]:
    """
    Quick local scan for common security anti-patterns.
    No AI call – pure regex for speed.
    """
    RISK_PATTERNS = [
        (r"(?:password|secret|api_key|apikey|token)\s*=\s*['\"][^'\"]{4,}['\"]", "Hardcoded Secret", "critical"),
        (r"eval\s*\(", "eval() Usage", "high"),
        (r"exec\s*\(", "exec() Usage", "high"),
        (r"shell=True", "Shell Injection Risk", "high"),
        (r"SELECT\s+.+\s+FROM.+\+", "Potential SQL Injection", "critical"),
        (r"innerHTML\s*=", "XSS Risk via innerHTML", "high"),
        (r"document\.write\(", "XSS Risk via document.write", "medium"),
        (r"http://(?!localhost|127)", "Non-HTTPS URL", "medium"),
        (r"TODO|FIXME|HACK|XXX", "Technical Debt Marker", "low"),
        (r"console\.log\(", "Debug Console.log", "low"),
    ]

    COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), l, s) for p, l, s in RISK_PATTERNS]

    findings = []
    for path, data in files.items():
        # Only scan first 4KB to save massive regex CPU cycles
        content = data.get("content", "")[:4000]
        if not content:
            continue
        for pattern, label, severity in COMPILED_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                findings.append({
                    "file": path,
                    "risk": label,
                    "severity": severity,
                    "occurrences": len(matches),
                })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 4))
    return findings[:30]  # cap at 30
