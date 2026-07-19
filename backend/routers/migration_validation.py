"""
Migration Validation Router — REST Endpoints for Phase 4 (Validation & Approval)
===============================================================================
Validates the Phase 3 generated output and drives the approval workflow whose
result Phase 5 (Apply Migration) will consume. Nothing here modifies, compiles,
applies, exports, or deletes anything — validation and approval decisions only.

Mounted at the /api/migration prefix; all routes live under /validate so they
never collide with the Phase 2 (/analyze…) or Phase 3 (/generate…) routes.
"""

import logging
from fastapi import APIRouter, HTTPException, Query

from backend.models.schemas import (
    ValidationStatusResponse,
    ApprovalActionRequest,
    ApprovalOutput,
)
from backend.services.migration_validation_service import migration_validation_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate", summary="Run validation on the generated migration output")
async def start_validation():
    """
    Validate the current Phase 3 generation session (syntax, dependencies,
    architecture, configuration, consistency, risk). Does not re-run migration
    or regenerate code.
    """
    try:
        migration_validation_service.trigger_validation()
        return {"success": True, "message": "Migration validation initiated."}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to initiate validation: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/validate/status", response_model=ValidationStatusResponse,
            summary="Get validation status & report")
async def validation_status():
    try:
        return migration_validation_service.get_status()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to fetch validation status: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/validate/file", summary="Get one file's validation result + content (Issue Viewer)")
async def validation_file(path: str = Query(..., description="Generated file path")):
    data = migration_validation_service.get_file_result(path)
    if not data:
        raise HTTPException(status_code=404, detail=f"No validation result for: {path}")
    return {"success": True, **data}


@router.post("/validate/approve", summary="Approve a single file")
async def approve_file(req: ApprovalActionRequest):
    return migration_validation_service.approve_file(req.path)


@router.post("/validate/reject", summary="Reject a single file")
async def reject_file(req: ApprovalActionRequest):
    return migration_validation_service.reject_file(req.path)


@router.post("/validate/approve-safe", summary="Approve all safe (auto-approvable) files")
async def approve_all_safe():
    return migration_validation_service.approve_all_safe()


@router.post("/validate/reject-all", summary="Reject the entire migration")
async def reject_migration():
    return migration_validation_service.reject_migration()


@router.get("/validate/approval", response_model=ApprovalOutput,
            summary="Get the approval output (consumed by Phase 5)")
async def approval_output():
    return migration_validation_service.get_approval_output()


@router.post("/validate/reset", summary="Reset the validation session")
async def validation_reset():
    migration_validation_service.reset()
    return {"success": True, "message": "Validation state reset."}
