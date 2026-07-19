import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any

from backend.services.impact_service import impact_service
from backend.routers.filesystem import get_project_root
from backend.services.analysis_service import analysis_manager
from backend.services.search_service import search_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/analyze", summary="Perform direct and indirect impact analysis of a target change")
async def analyze_impact(
    type: str = Query(..., description="Target component type: file, class, function, module, api"),
    target: str = Query(..., min_length=1, description="Name or path of target component"),
    project_root: str = Depends(get_project_root)
):
    """
    Traces direct and indirect dependents for a file, class, function, module, or API.
    Scores risk levels and returns the dependency chain explanation.
    """
    try:
        summary = impact_service.get_change_summary(target, project_root)
        return summary
    except Exception as exc:
        logger.error(f"Impact analysis failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/risk", summary="Get change risk score and statistics")
async def check_risk(
    target: str = Query(..., min_length=1, description="Name or path of component"),
    project_root: str = Depends(get_project_root)
):
    """
    Calculates change risk indicators, warning metrics, and description explanations.
    """
    try:
        summary = impact_service.get_change_summary(target, project_root)
        return {
            "target": target,
            "type": summary.get("type", "unknown"),
            "risk": summary.get("summary", {}).get("risk", {
                "level": "Low",
                "explanation": "No matching target was found to assess.",
                "metrics": {"affected_files_count": 0, "critical_modules_hit": 0, "circular_dependencies_involved": 0}
            })
        }
    except Exception as exc:
        logger.error(f"Risk assessment failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/graph", summary="Get full node-edge dependency graph data for UI rendering")
async def get_graph(project_root: str = Depends(get_project_root)):
    """
    Builds and returns all node-edge relations encompassing modules, files, classes,
    functions/methods, and API endpoints. Useful for interactive UI visualization.
    """
    try:
        impact_service.ensure_graph_ready(project_root)
        
        nodes = []
        edges = []
        
        # 1. Add Modules
        for m, files in analysis_manager.modules.items():
            nodes.append({
                "id": f"module::{m}",
                "label": m,
                "title": f"Module: {m}",
                "group": "module"
            })
            for f in files:
                edges.append({
                    "from": f,
                    "to": f"module::{m}",
                    "arrows": "none",
                    "label": "contains",
                    "dashes": True
                })

        # 2. Add Files & File Imports
        for f in impact_service.file_dependents.keys():
            nodes.append({
                "id": f,
                "label": f.split('/')[-1],
                "title": f"File: {f}",
                "group": "file",
                "file": f,
                "line": 1
            })
            for dep in impact_service.file_dependencies.get(f, []):
                edges.append({
                    "from": dep,
                    "to": f,
                    "arrows": "to",
                    "label": "imports"
                })

        # 3. Add Classes & Inheritance
        for cls, meta in impact_service.defined_classes.items():
            nodes.append({
                "id": f"class::{cls}",
                "label": cls,
                "title": f"Class: {cls} (in {meta['file']})",
                "group": "class",
                "file": meta["file"],
                "line": meta["line"]
            })
            # Inheritance edges
            for base in meta["bases"]:
                if base in impact_service.defined_classes:
                    edges.append({
                        "from": f"class::{base}",
                        "to": f"class::{cls}",
                        "arrows": "to",
                        "label": "inherits"
                    })
            # Defined in file reference edge
            edges.append({
                "from": f"class::{cls}",
                "to": meta["file"],
                "arrows": "none",
                "label": "defined_in",
                "dashes": True
            })

        # 4. Add Functions/Methods & Call lines
        for sig, meta in impact_service.defined_funcs.items():
            nodes.append({
                "id": f"func::{sig}",
                "label": meta["name"],
                "title": f"Function: {sig}",
                "group": "function",
                "file": meta["file"],
                "line": meta["line"]
            })
            # Function calls (edge goes from callee to caller)
            for caller in impact_service.func_dependents.get(sig, []):
                edges.append({
                    "from": f"func::{sig}",
                    "to": f"func::{caller}",
                    "arrows": "to",
                    "label": "calls"
                })
            # Member reference link
            parent_id = f"class::{meta['class']}" if meta["class"] else meta["file"]
            edges.append({
                "from": f"func::{sig}",
                "to": parent_id,
                "arrows": "none",
                "label": "member_of",
                "dashes": True
            })

        # 5. Add APIs & Controller linkages
        for api in search_service.apis:
            api_id = f"api::{api['endpoint']}"
            nodes.append({
                "id": api_id,
                "label": f"{api['method']} {api['endpoint']}",
                "title": f"API: {api['method']} {api['endpoint']}\n{api['purpose']}",
                "group": "api",
                "file": api["file"],
                "line": api["line"]
            })
            
            # Controller mapping
            api_file = api["file"]
            api_line = api["line"]
            for sig, meta in impact_service.defined_funcs.items():
                if meta["file"] == api_file and (meta["line"] - 3 <= api_line <= meta["line_end"]):
                    edges.append({
                        "from": f"func::{sig}",
                        "to": api_id,
                        "arrows": "to",
                        "label": "handles"
                    })

        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.error(f"Failed to generate dependency graph: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
