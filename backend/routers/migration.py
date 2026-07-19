"""
Migration Router — REST Endpoints for AI Code Migration Analysis Engine (Phase 2)
=================================================================================
Provides endpoints to trigger project analysis, query scan progress, and retrieve
generated Migration Plans.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from backend.models.schemas import (
    MigrationAnalysisRequest,
    MigrationStatusResponse,
    MigrationPlan
)
from backend.services.migration_service import migration_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", summary="Trigger project migration analysis")
async def analyze_migration(
    req: MigrationAnalysisRequest,
    project_root: str = Depends(get_project_root)
):
    """
    Triggers deterministic background migration analysis for the active project
    according to the specified migration scope and configuration options.
    """
    try:
        migration_service.trigger_analysis(project_root, req)
        return {"success": True, "message": "Migration analysis initiated."}
    except Exception as exc:
        logger.error(f"Failed to initiate migration analysis: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", response_model=MigrationStatusResponse, summary="Get migration analysis status")
async def get_migration_status():
    """
    Returns current scanner progress, step logs, active step name,
    and generated Migration Plan once complete.
    """
    try:
        return migration_service.get_status_summary()
    except Exception as exc:
        logger.error(f"Failed to fetch migration status: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/plan", summary="Get generated Migration Plan")
async def get_migration_plan():
    """
    Returns the complete active Migration Plan object if available.
    """
    plan = migration_service.active_plan
    if not plan:
        return {"success": False, "message": "No active migration plan available.", "plan": None}
    return {"success": True, "plan": plan}
