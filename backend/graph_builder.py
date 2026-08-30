import math
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from itertools import islice

# ── file-type → colour mapping ──────────────────────────────────────────────────
EXT_COLORS = {
    "py":    "#4B8BBE",
    "js":    "#F7DF1E",
    "jsx":   "#61DAFB",
    "ts":    "#3178C6",
    "tsx":   "#61DAFB",
    "java":  "#ED8B00",
    "go":    "#00ADD8",
    "rs":    "#CE422B",
    "cpp":   "#659AD2",
    "c":     "#A8B9CC",
    "cs":    "#239120",
    "rb":    "#CC342D",
    "php":   "#8892BF",
    "html":  "#E34F26",
    "css":   "#1572B6",
    "scss":  "#CD6799",
    "json":  "#888",
    "yaml":  "#888",
    "yml":   "#888",
    "md":    "#888",
    "sh":    "#4EAA25",
    "sql":   "#F29111",
    "vue":   "#42B883",
    "svelte":"#FF3E00",
}
DEFAULT_COLOR = "#6B7280"

# ── complexity scoring ─────────────────────────────────────────────────────────
def _complexity_score(file_data: dict) -> float:
    lines = file_data.get("lines", 0)
    imports = len(file_data.get("imports", []))
    raw = math.log1p(lines) * 0.5 + imports * 0.3
    return min(round(raw, 1), 10.0)

# ── resolve import to file path ────────────────────────────────────────────────
def _resolve_import(importer: str, imp: str, all_paths: set[str], path_map: dict[str, str]) -> str | None:
    imp = imp.strip().replace("\\", "/")
    if not imp: return None
    
    base_dir = str(Path(importer).parent).replace("\\", "/")

    # 1. Relative imports
    if imp.startswith("."):
        try:
            target_path = str((Path(base_dir) / imp).resolve().relative_to(Path().resolve())).replace("\\", "/")
        except Exception:
            target_path = str(Path(base_dir) / imp).replace("\\", "/")
        
        candidates = [
            target_path,
            target_path + ".py", target_path + ".js", target_path + ".jsx", target_path + ".ts", target_path + ".tsx",
            target_path + "/index.js", target_path + "/index.jsx", target_path + "/index.ts", target_path + "/index.tsx"
        ]
        for c in candidates:
            if c in all_paths: return c
            
    # 2. Absolute / Package imports
    if imp in path_map: return path_map[imp]
    
    for ext in [".py", ".js", ".jsx", ".ts", ".tsx"]:
        if (imp + ext) in path_map: return path_map[imp + ext]

    name = imp.split(".")[-1].split("/")[-1]
    if name in path_map: return path_map[name]
    
    return None

def _get_module_id(path: str) -> str:
    """Gets the parent module ID for a given file path.
    e.g. src/services/auth.py -> module:src/services
    """
    parts = path.split("/")
    if len(parts) > 1:
        return "module:" + "/".join(parts[:-1])
    return "module:root"

# ── main builder ────────────────────────────────────────────────────────────────
def build_graph(files: dict[str, dict], imports: dict[str, list[str]], update_status=None) -> dict[str, Any]:
    if update_status: update_status("Building normalized knowledge graph...")
    
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    
    all_paths = set(files.keys())
    
    # Path map for imports resolution
    path_map = {}
    for p in all_paths:
        name = p.split("/")[-1]
        path_map[p] = p
        path_map[name] = p
        if "." in name:
            path_map[name.rsplit(".", 1)[0]] = p

    # 1. Create Repository Node
    nodes["repository:root"] = {
        "id": "repository:root",
        "type": "repository",
        "label": "Repository",
        "parent_id": None,
        "data": {}
    }

    # 2. Process Files & Create Module Nodes
    for path, data in files.items():
        category = data.get("category", "SOURCE")
        # For the knowledge graph, we include all files, but we flag them by category.
        
        # Determine module hierarchy
        parts = path.split("/")
        current_module = "repository:root"
        
        if len(parts) > 1:
            for i in range(1, len(parts)):
                mod_path = "/".join(parts[:i])
                mod_id = f"module:{mod_path}"
                if mod_id not in nodes:
                    nodes[mod_id] = {
                        "id": mod_id,
                        "type": "module",
                        "label": parts[i-1],
                        "parent_id": current_module,
                        "data": {"file_count": 0, "category_counts": {}}
                    }
                current_module = mod_id
                
        # Update module metrics
        if current_module != "repository:root":
            nodes[current_module]["data"]["file_count"] = nodes[current_module]["data"].get("file_count", 0) + 1
            cat_counts = nodes[current_module]["data"].get("category_counts", {})
            cat_counts[category] = cat_counts.get(category, 0) + 1
            nodes[current_module]["data"]["category_counts"] = cat_counts

        # Create File Node
        file_id = f"file:{path}"
        score = _complexity_score(data)
        ext = data.get("extension", "")
        
        nodes[file_id] = {
            "id": file_id,
            "type": "file",
            "label": data["name"],
            "parent_id": current_module,
            "data": {
                "extension": ext,
                "lines": data.get("lines", 0),
                "complexity": score,
                "color": EXT_COLORS.get(ext, DEFAULT_COLOR),
                "category": category,
                "path": path
            }
        }
        
        # Add CONTAINS edge from module to file
        edges.append({
            "id": f"e_contains_{current_module}_{file_id}",
            "source": current_module,
            "target": file_id,
            "type": "CONTAINS"
        })

    # 3. Process Import Edges
    if update_status: update_status("Connecting dependency edges...")
    for importer, imp_list in imports.items():
        source_id = f"file:{importer}"
        if source_id not in nodes:
            continue
            
        for imp in imp_list:
            target_path = _resolve_import(importer, imp, all_paths, path_map)
            if target_path and target_path != importer:
                target_id = f"file:{target_path}"
                edges.append({
                    "id": f"e_imports_{source_id}_{target_id}",
                    "source": source_id,
                    "target": target_id,
                    "type": "IMPORTS"
                })

    # 4. Metrics
    file_nodes = [n for n in nodes.values() if n["type"] == "file"]
    important_files = sorted(file_nodes, key=lambda n: n["data"].get("complexity", 0), reverse=True)[:5]
    
    # Calculate simple in-degree for importance (using IMPORTS edges)
    in_degrees = {}
    for edge in edges:
        if edge["type"] == "IMPORTS":
            in_degrees[edge["target"]] = in_degrees.get(edge["target"], 0) + 1
            
    important_files = sorted(file_nodes, key=lambda n: in_degrees.get(n["id"], 0) + n["data"].get("complexity", 0), reverse=True)[:5]

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "metrics": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "graph_truncated": False,
            "circular_dependency_count": 0, # Cycles calculation can be deferred or handled by graph DB/algorithms
            "circular_dependencies": [],
            "important_files": [{"path": n["data"]["path"], "label": n["label"], "complexity": n["data"].get("complexity", 0)} for n in important_files],
            "avg_complexity": round(sum(n["data"].get("complexity", 0) for n in file_nodes) / max(len(file_nodes), 1), 2),
        },
    }
