"""
Migration Orchestrator Router — Phase 6: Workflow Orchestration Endpoints
========================================================================
Exposes endpoints for initiating, monitoring, cancelling, and reviewing
end-to-end code migration workflows under /api/migration/workflow.
"""

from __future__ import annotations
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query

from backend.models.schemas import (
    WorkflowStartRequest,
    WorkflowStatusResponse,
    UnifiedDashboardResponse,
    ArchivedMigrationReport,
)
from backend.services.migration_orchestrator import migration_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/workflow/start", response_model=Dict[str, Any])
async def start_workflow(req: WorkflowStartRequest):
    """Start (or restart) an end-to-end orchestrated migration workflow."""
    try:
        migration_orchestrator.trigger_workflow(req)
        return {
            "success": True,
            "message": "Migration workflow initiated.",
            "workflow_id": migration_orchestrator.workflow_id,
        }
    except Exception as exc:
        logger.error(f"Error starting migration workflow: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/workflow/status", response_model=WorkflowStatusResponse)
async def get_workflow_status():
    """Return current workflow status, global progress, live log stream, and dashboard metrics."""
    return migration_orchestrator.get_workflow_status()


@router.post("/workflow/cancel", response_model=Dict[str, Any])
async def cancel_workflow():
    """Safely cancel active migration workflow execution."""
    migration_orchestrator.cancel_workflow()
    return {"success": True, "message": "Migration workflow cancelled."}


@router.get("/workflow/dashboard", response_model=UnifiedDashboardResponse)
async def get_unified_dashboard():
    """Return complete enterprise dashboard summary across all migration modules."""
    return migration_orchestrator.get_dashboard_summary()


@router.get("/workflow/history/{migration_id}/report", response_model=ArchivedMigrationReport)
async def get_archived_report(migration_id: str):
    """Retrieve complete historical report for reopening past migration runs."""
    report = migration_orchestrator.get_archived_report(migration_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Migration record '{migration_id}' not found.")
    return report
