"""
Source Router (Phase 7) — Source Code Update & Final Integration.

  POST /api/source/apply      apply an approved+validated bundle to disk
  POST /api/source/undo       undo the last applied operation
  POST /api/source/rollback   roll back a specific operation
  GET  /api/source/history    change history (newest first)
  GET  /api/source/backups    available backups
  GET  /api/source/git-status optional Git detection

apply/undo/rollback refresh the workspace (analysis, search, impact, tree) so the
IDE immediately reflects the updated files.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.services.source_update_service import source_update_service
from backend.services import file_service
from backend.services.analysis_service import analysis_manager
from backend.services.search_service import search_service
from backend.services.impact_service import impact_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)
router = APIRouter()


class ApplyRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    commit: bool = False


class RollbackRequest(BaseModel):
    operation_id: str = Field(..., min_length=1)


async def _refresh_workspace(project_root: str) -> dict:
    """Re-analyze (incrementally) and rebuild indexes after a disk change."""
    try:
        await analysis_manager.run_analysis(project_root)
    except Exception as exc:
        logger.warning(f"Workspace refresh: analysis failed: {exc}")
    try:
        search_service.build_index(project_root)
    except Exception as exc:
        logger.warning(f"Workspace refresh: search index failed: {exc}")
    try:
        impact_service.ensure_graph_ready(project_root)
    except Exception as exc:
        logger.warning(f"Workspace refresh: impact graph failed: {exc}")
    try:
        tree = file_service.get_tree(project_root, depth=1).model_dump()
    except Exception:
        tree = None
    return {"tree": tree, "stats": analysis_manager.stats}


@router.post("/apply", summary="Apply an approved change set to disk")
async def apply(body: ApplyRequest, project_root: str = Depends(get_project_root)):
    try:
        result = source_update_service.apply(body.plan_id, project_root, do_commit=body.commit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Apply failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("status") == "SUCCESS":
        result["refresh"] = await _refresh_workspace(project_root)
    return result


@router.post("/undo", summary="Undo the last applied change set")
async def undo(project_root: str = Depends(get_project_root)):
    try:
        result = source_update_service.undo_last(project_root)
    except Exception as exc:
        logger.error(f"Undo failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    if result.get("status") == "UNDONE":
        result["refresh"] = await _refresh_workspace(project_root)
    return result


@router.post("/rollback", summary="Roll back a specific operation")
async def rollback(body: RollbackRequest, project_root: str = Depends(get_project_root)):
    try:
        result = source_update_service.rollback(body.operation_id, project_root)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Rollback failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    if result.get("status") == "UNDONE":
        result["refresh"] = await _refresh_workspace(project_root)
    return result


@router.get("/history", summary="List the change history")
async def history(project_root: str = Depends(get_project_root)):
    return {"history": source_update_service.get_history(project_root)}


@router.get("/backups", summary="List available backups")
async def backups(project_root: str = Depends(get_project_root)):
    return {"backups": source_update_service.get_backups(project_root)}


@router.get("/git-status", summary="Detect Git repository state (optional)")
async def git_status(project_root: str = Depends(get_project_root)):
    return source_update_service.git_status(project_root)
