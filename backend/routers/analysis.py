import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.services.analysis_service import analysis_manager
from backend.services.ai_service import ai_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)
router = APIRouter()

class ExplainRequest(BaseModel):
    scope: str
    target: str
    active_file: Optional[str] = None
    cursor_line: Optional[int] = None

@router.post("/analyze", summary="Trigger background analysis of the active project")
async def analyze_project(project_root: str = Depends(get_project_root)):
    """
    Kicks off or restarts the asynchronous project scan.
    Returns immediately since parsing executes in the background.
    """
    try:
        analysis_manager.trigger_analysis(project_root)
        return {"success": True, "message": "Analysis initiated."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/status", summary="Get status and stats of the project analysis")
async def get_status():
    """
    Returns current scanner progress, current file, total counts,
    and detected language breakdown percentages.
    """
    return analysis_manager.get_status_summary()

@router.post("/explain", summary="Generate explanation for a specific codebase target")
async def explain_code(body: ExplainRequest):
    """
    Explains the target (project/module/file/class/function) utilizing
    available contextual metadata and API integrations.
    """
    try:
        explanation = ai_service.explain(
            scope=body.scope,
            target=body.target,
            active_file=body.active_file,
            cursor_line=body.cursor_line
        )
        return {"success": True, "explanation": explanation}
    except Exception as exc:
        logger.error(f"Explain target failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
