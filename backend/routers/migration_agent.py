"""
Migration Agent Router — REST Endpoints for the AI Migration Agent (Phase 3)
============================================================================
Triggers AI code generation from the active Phase 2 Migration Plan, reports
real-time generation progress, serves individual generated files (with diffs)
for the read-only comparison view, and exposes the hand-off envelope for later
phases (Phase 4 validation, Phase 5 apply, Phase 6 integration).

Mounted at the same /api/migration prefix as the Phase 2 analysis router; the
Phase 3 routes all live under /generate so they never collide with Phase 2.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Response

from backend.models.schemas import (
    MigrationGenerateRequest,
    MigrationGenerationStatus,
)
from backend.services.migration_agent_service import migration_agent_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate", summary="Start AI code migration generation")
async def start_generation(
    req: MigrationGenerateRequest,
    project_root: str = Depends(get_project_root),
):
    """
    Kick off background AI code generation for the active Migration Plan.

    Reuses the Phase 2 analysis output (no rescan), talks only through the
    provider interface, and writes generated code to an isolated staging
    workspace — the original project is never modified.
    """
    try:
        migration_agent_service.trigger_generation(project_root, req)
        return {"success": True, "message": "AI migration generation initiated."}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to initiate migration generation: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/generate/status",
    response_model=MigrationGenerationStatus,
    summary="Get AI migration generation status",
)
async def generation_status():
    """Return generation progress, step logs, summary counters, and file list."""
    try:
        return migration_agent_service.get_status()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to fetch generation status: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/generate/file", summary="Get a single generated file (content + diff)")
async def generation_file(
    path: str = Query(..., description="Generated file path (relative to staging root)"),
):
    """Return the full generated file payload for the code-comparison view."""
    gen = migration_agent_service.get_file(path)
    if not gen:
        raise HTTPException(status_code=404, detail=f"Generated file not found: {path}")
    return {"success": True, "file": gen}


@router.get("/generate/handoff", summary="Get the Phase 4/5/6 hand-off envelope")
async def generation_handoff():
    """Return the extension-point hand-off object for downstream phases."""
    handoff = migration_agent_service.get_handoff()
    if not handoff:
        return {"success": False, "message": "No completed migration to hand off.", "handoff": None}
    return {"success": True, "handoff": handoff}


@router.post("/generate/reset", summary="Reset the current generation session")
async def generation_reset():
    """Clear in-memory generation state (staged files on disk are left intact)."""
    migration_agent_service.reset()
    return {"success": True, "message": "Migration generation state reset."}


# ---------------------------------------------------------------------------
# Download Migrated Output Endpoints
# ---------------------------------------------------------------------------

@router.get("/download/project", summary="Download entire migrated project as ZIP")
async def download_project_zip():
    """Download a ZIP archive containing all generated files in the staging workspace."""
    try:
        zip_bytes, filename, size = migration_agent_service.get_project_zip()
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/download/folder", summary="Download a specific migrated folder as ZIP")
async def download_folder_zip(
    path: str = Query(..., description="Folder path in staging workspace"),
):
    """Download a ZIP archive of a specific folder in the staging workspace."""
    try:
        zip_bytes, filename, size = migration_agent_service.get_folder_zip(path)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/download/file", summary="Download a single migrated file as ZIP")
async def download_file_zip(
    path: str = Query(..., description="File path in staging workspace"),
):
    """Download a ZIP archive containing a single generated file."""
    try:
        zip_bytes, filename, size = migration_agent_service.get_file_zip(path)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/download/info", summary="Get download ZIP size and file count info")
async def download_info(
    type: str = Query("project", description="Download type: file, folder, project"),
    path: Optional[str] = Query(None, description="Optional relative path"),
):
    """Get ZIP file size and count metadata before downloading."""
    return migration_agent_service.get_download_info(type, path)

