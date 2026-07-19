"""
Validation Router (Phase 6) — Validation & Approval endpoints.

  POST /api/validation/validate         run the validation pipeline on a bundle
  GET  /api/validation/report/{plan_id} fetch a cached validation report
  POST /api/validation/approve          record approval (no file writes)
  POST /api/validation/reject           record rejection
  GET  /api/validation/decision/{plan_id} current approval state

Nothing here modifies project source files — application happens in Phase 7.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.services.validation_service import validation_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)
router = APIRouter()


class PlanRef(BaseModel):
    plan_id: str = Field(..., min_length=1)
    force: bool = False


@router.post("/validate", summary="Run the validation pipeline on a proposed change set")
async def validate(body: PlanRef, project_root: str = Depends(get_project_root)):
    try:
        return validation_service.validate(body.plan_id, project_root, force=body.force)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Validation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/report/{plan_id}", summary="Fetch a cached validation report")
async def get_report(plan_id: str):
    report = validation_service.get_report(plan_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"No validation report for plan_id: {plan_id}")
    return report


@router.post("/approve", summary="Record approval of a validated change set")
async def approve(body: PlanRef):
    try:
        return validation_service.approve(body.plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/reject", summary="Record rejection of a change set")
async def reject(body: PlanRef):
    try:
        return validation_service.reject(body.plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/decision/{plan_id}", summary="Get the current approval decision")
async def decision(plan_id: str):
    return validation_service.get_decision(plan_id)
