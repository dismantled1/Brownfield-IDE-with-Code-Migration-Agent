"""
Migration Application Router — REST Endpoints for Phase 5 (Apply / Rollback / History)
=====================================================================================
Applies APPROVED migrated code into the project (with backups + rollback), and
serves the change-set preview and migration history. Consumes prior-phase output
only — never regenerates code, re-analyzes, or re-validates.

Mounted at the /api/migration prefix; routes never collide with Phase 2/3/4.
"""

import logging
from fastapi import APIRouter, HTTPException

from backend.models.schemas import ApplyRequest, RollbackRequest, ChangeSet, FinalReport
from backend.services.migration_apply_service import migration_apply_service, MigrationApplyError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/changes", response_model=ChangeSet, summary="Preview the apply change set")
async def get_changes():
    """Return the create/replace/modify/delete/rename preview for approved files."""
    try:
        return migration_apply_service.build_change_set()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to build change set: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/apply", response_model=FinalReport, summary="Apply the approved migration")
async def apply_migration(req: ApplyRequest):
    """
    Back up originals, then write approved files into the project. Returns the
    final report (drives the success screen). Fully reversible via /rollback.
    """
    try:
        return migration_apply_service.apply(applied_by=req.applied_by)
    except MigrationApplyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Apply failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/rollback", summary="Roll back a migration (whole or single file)")
async def rollback_migration(req: RollbackRequest):
    try:
        return migration_apply_service.rollback(req.migration_id, file=req.file)
    except MigrationApplyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Rollback failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="List migration application history")
async def get_history():
    return {"success": True, "history": [r.model_dump() for r in migration_apply_service.get_history()]}
