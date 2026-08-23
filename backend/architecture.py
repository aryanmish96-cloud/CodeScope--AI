"""
architecture.py – Detect tech stack, architecture layers, and generate architecture overview.
Evidence-backed: every detected component includes file references.
No phantom Frontend/Database nodes when they are not actually present.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any


# ── Tech Stack Detectors ────────────────────────────────────────────────────────
STACK_SIGNALS: list[tuple[str, str, str]] = [
    # (file_pattern, keyword_in_file | None, tech_label)
    ("package.json",    "react",        "React"),
    ("package.json",    "next",         "Next.js"),
    ("package.json",    "vue",          "Vue.js"),
    ("package.json",    "svelte",       "Svelte"),
    ("package.json",    "angular",      "Angular"),
    ("package.json",    "express",      "Express.js"),
    ("package.json",    "fastify",      "Fastify"),
    ("package.json",    "typescript",   "TypeScript"),
    ("package.json",    "tailwindcss",  "Tailwind CSS"),
    ("requirements.txt","fastapi",      "FastAPI"),
    ("requirements.txt","django",       "Django"),
    ("requirements.txt","flask",        "Flask"),
    ("requirements.txt","sqlalchemy",   "SQLAlchemy"),
    ("requirements.txt","celery",       "Celery"),
    ("requirements.txt","pytorch",      "PyTorch"),
    ("requirements.txt","tensorflow",   "TensorFlow"),
    ("requirements.txt","anthropic",    "Claude AI"),
    ("requirements.txt","openai",       "OpenAI"),
    ("requirements.txt","groq",         "Groq AI"),
    ("pom.xml",         "spring-boot",  "Spring Boot"),
    ("pom.xml",         "hibernate",    "Hibernate"),
    ("go.mod",          None,           "Go"),
    ("Cargo.toml",      None,           "Rust"),
    ("Gemfile",         "rails",        "Ruby on Rails"),
    ("composer.json",   "laravel",      "Laravel"),
    ("pubspec.yaml",    "flutter",      "Flutter"),
    ("docker-compose",  None,           "Docker Compose"),
    ("Dockerfile",      None,           "Docker"),
    ("kubernetes",      None,           "Kubernetes"),
    (".github/workflows", None,         "GitHub Actions"),
]

DB_SIGNALS = {
    "postgres": "PostgreSQL",
    "mysql":    "MySQL",
    "sqlite":   "SQLite",
    "mongodb":  "MongoDB",
    "redis":    "Redis",
    "supabase": "Supabase",
    "prisma":   "Prisma",
    "mongoose": "MongoDB",
    "firebase": "Firebase",
    "dynamodb": "DynamoDB",
    "cassandra":"Cassandra",
    "elasticsearch": "Elasticsearch",
}

LAYER_PATTERNS = {
    "frontend": [
        r"src/components", r"src/pages", r"src/views", r"public/",
        r"\.jsx?$", r"\.tsx?$", r"\.vue$", r"\.svelte$",
        r"index\.html", r"App\.(jsx?|tsx?)",
    ],
    "backend": [
        r"api/", r"routes/", r"controllers/", r"middleware/",
        r"server\.(js|ts|py)$", r"main\.(py|go|rs|java)$",
        r"app\.(py|js|ts)$", r"manage\.py$",
    ],
    "database": [
        r"migrations/", r"models/", r"schema\.(sql|prisma|graphql)$",
        r"db/", r"database/", r"\.sql$",
    ],
    "tests": [
        r"test/", r"tests/", r"__tests__/", r"spec/",
        r"\.test\.(js|ts|py)$", r"\.spec\.(js|ts)$",
    ],
    "infrastructure": [
        r"\.github/", r"Dockerfile", r"docker-compose",
        r"kubernetes/", r"k8s/", r"terraform/", r"\.yaml$",
    ],
}

# Mermaid node shapes per component type
_MERMAID_SHAPES = {
    "frontend":       lambda label: f'["{label}"]',
    "backend":        lambda label: f'["{label}"]',
    "database":       lambda label: f'[("{label}")]',  # cylinder
    "tests":          lambda label: f'["{label}"]',
    "infrastructure": lambda label: f'["{label}"]',
    "queue":          lambda label: f'["{label}"]',
    "ml":             lambda label: f'["{label}"]',
    "cli":            lambda label: f'["{label}"]',
    "other":          lambda label: f'["{label}"]',
}

_MERMAID_COLORS = {
    "frontend":       "#3b82f6",
    "backend":        "#7c3aed",
    "database":       "#f97316",
    "tests":          "#10b981",
    "infrastructure": "#6b7280",
    "other":          "#9ca3af",
}


def _file_contains(content: str, keyword: str) -> bool:
    return keyword.lower() in content.lower()


def _find_evidence_line(content: str, keyword: str) -> int | None:
    """Return the 1-indexed line number where keyword first appears."""
    for i, line in enumerate(content.split("\n"), 1):
        if keyword.lower() in line.lower():
            return i
    return None


def detect_architecture(files: dict[str, dict]) -> dict[str, Any]:
    """
    Scan all file paths and contents to detect:
    - Tech stack (with file evidence)
    - Architecture layers (with file evidence)
    - Database tech (with file evidence)
    - Project type

    Returns evidence for every detected component so the UI can show
    "Verified – 3 evidence locations" instead of phantom nodes.
    """
    tech_stack: list[str] = []
    tech_evidence: dict[str, list[dict]] = {}  # label → [{file, line, reason}]

    layers_detected: dict[str, bool] = {
        "frontend": False,
        "backend": False,
        "database": False,
        "tests": False,
        "infrastructure": False,
    }
    layer_evidence: dict[str, list[dict]] = {k: [] for k in layers_detected}

    databases: list[str] = []
    db_evidence: dict[str, list[dict]] = {}

    all_paths = list(files.keys())
    path_str = "\n".join(all_paths)

    # ── Detect tech stack with evidence ────────────────────────────────────────
    for file_pattern, keyword, label in STACK_SIGNALS:
        for path, data in files.items():
            if file_pattern.lower() not in path.lower():
                continue
            content = data.get("content", "")
            if keyword is None:
                if label not in tech_stack:
                    tech_stack.append(label)
                    tech_evidence[label] = [{"file": path, "line": 1, "reason": f"File '{path}' detected"}]
                break
            else:
                if _file_contains(content, keyword):
                    if label not in tech_stack:
                        tech_stack.append(label)
                        ln = _find_evidence_line(content, keyword) or 1
                        tech_evidence[label] = [{"file": path, "line": ln, "reason": f"'{keyword}' found in {path}"}]
                    break

    # ── Detect layers with evidence ────────────────────────────────────────────
    for layer, patterns in LAYER_PATTERNS.items():
        for pattern in patterns:
            for path in all_paths:
                if re.search(pattern, path, re.IGNORECASE):
                    layers_detected[layer] = True
                    layer_evidence[layer].append({
                        "file": path,
                        "line": 1,
                        "reason": f"path matches '{pattern}'",
                    })
                    if len(layer_evidence[layer]) >= 3:
                        break
            if layers_detected[layer]:
                break

    # ── Detect databases with evidence ─────────────────────────────────────────
    for keyword, db_name in DB_SIGNALS.items():
        for path, data in files.items():
            content = data.get("content", "")[:3000]
            if keyword in content.lower():
                if db_name not in databases:
                    databases.append(db_name)
                    ln = _find_evidence_line(content, keyword) or 1
                    db_evidence[db_name] = [{"file": path, "line": ln, "reason": f"'{keyword}' found in {path}"}]
                break

    # ── Determine project type from verified layers only ───────────────────────
    if layers_detected["frontend"] and layers_detected["backend"]:
        project_type = "Full-Stack Application"
    elif layers_detected["frontend"]:
        project_type = "Frontend Application"
    elif layers_detected["backend"]:
        project_type = "Backend / API Service"
    elif "Go" in tech_stack or "Rust" in tech_stack:
        project_type = "Systems / CLI Application"
    else:
        project_type = "Library / Package"

    # ── Build architecture flow (only verified layers) ─────────────────────────
    flow_steps = _build_flow(layers_detected, tech_stack, databases)

    # ── Build verified mermaid diagram ─────────────────────────────────────────
    mermaid = build_verified_mermaid(layers_detected, tech_stack, databases)

    return {
        "tech_stack": tech_stack,
        "tech_evidence": tech_evidence,
        "databases": databases,
        "db_evidence": db_evidence,
        "layers": layers_detected,
        "layer_evidence": layer_evidence,
        "project_type": project_type,
        "architecture_flow": flow_steps,
        "active_layers": [l for l, v in layers_detected.items() if v],
        "mermaid_diagram": mermaid,
    }


def build_verified_mermaid(
    layers: dict[str, bool],
    stack: list[str],
    databases: list[str],
) -> str:
    """
    Build a Mermaid diagram ONLY from verified detected components.
    NEVER adds Frontend, Backend, or Database nodes unless they were actually detected.
    """
    lines = ["graph TD"]
    node_ids: list[str] = []

    # Frontend node – only if frontend layer detected
    if layers.get("frontend"):
        fe_label = next((s for s in stack if s in {"React", "Vue.js", "Next.js", "Angular", "Svelte"}), "Frontend")
        lines.append(f'  FE["{fe_label}"]')
        node_ids.append("FE")

    # Backend node – only if backend layer detected
    if layers.get("backend"):
        be_label = next(
            (s for s in stack if s in {"FastAPI", "Django", "Flask", "Express.js", "Fastify", "Spring Boot", "Ruby on Rails", "Laravel"}),
            "API Server",
        )
        lines.append(f'  BE["{be_label}"]')
        node_ids.append("BE")

    # Database nodes – only if detected
    for i, db in enumerate(databases[:2]):
        nid = f"DB{i}"
        lines.append(f'  {nid}[("{db}")]')
        node_ids.append(nid)

    # Infrastructure – only if detected
    if layers.get("infrastructure"):
        infra_label = next((s for s in stack if s in {"Docker", "Docker Compose", "Kubernetes"}), "Infrastructure")
        lines.append(f'  INFRA["{infra_label}"]')
        node_ids.append("INFRA")

    # If nothing detected at all, show a generic node
    if not node_ids:
        lang = next((s for s in stack if s in {"Go", "Rust", "Python", "TypeScript"}), None)
        label = f"{lang} Package" if lang else "Repository"
        lines.append(f'  REPO["{label}"]')
        return "\n".join(lines)

    # Add edges: FE → BE → DB → INFRA (only between existing nodes)
    edges = []
    prev = None
    for nid in node_ids:
        if prev:
            edges.append(f"  {prev} --> {nid}")
        prev = nid

    lines.extend(edges)
    return "\n".join(lines)


def _build_flow(
    layers: dict[str, bool],
    stack: list[str],
    dbs: list[str],
) -> list[dict]:
    """
    Build a simple request-flow diagram description.
    Only adds a step when the corresponding layer was actually detected.
    """
    steps = []

    if layers["frontend"]:
        fe_label = next((s for s in stack if s in {"React", "Vue.js", "Next.js", "Angular", "Svelte"}), "Client / Browser")
        steps.append({"label": fe_label, "type": "client", "icon": "🌐"})

    if layers["backend"]:
        be_label = next(
            (s for s in stack if s in {"FastAPI", "Django", "Flask", "Express.js", "Fastify", "Spring Boot"}),
            "API Server",
        )
        steps.append({"label": be_label, "type": "api", "icon": "⚙️"})
    elif layers["infrastructure"] and not layers["frontend"] and not layers["backend"]:
        steps.append({"label": "Service", "type": "api", "icon": "⚙️"})

    if dbs:
        steps.append({"label": " / ".join(dbs[:2]), "type": "database", "icon": "🗄️"})

    if layers["infrastructure"]:
        infra_label = next((s for s in stack if s in {"Docker", "Docker Compose", "Kubernetes"}), "Infrastructure")
        steps.append({"label": infra_label, "type": "infra", "icon": "☁️"})

    return steps
