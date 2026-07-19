"""
Workspace Router — endpoints for project open/close and recent projects.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    OpenProjectRequest,
    OpenProjectResponse,
    WorkspaceState,
    SuccessResponse,
)
from backend.services import workspace_service, file_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/state", response_model=WorkspaceState, summary="Get workspace state")
async def get_state():
    """Return the current workspace state (active project, recent projects)."""
    return workspace_service.get_state()


@router.post("/open", response_model=OpenProjectResponse, summary="Open a project folder")
async def open_project(body: OpenProjectRequest):
    """
    Open a project by its absolute filesystem path.
    Validates the path exists, updates recent projects, and returns the
    shallow project tree (depth=1).
    """
    project_path = Path(body.path).resolve()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {body.path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {body.path}")

    try:
        workspace_service.open_project(str(project_path))
        tree = file_service.get_tree(str(project_path), depth=1)
    except Exception as exc:
        logger.error(f"Failed to open project {project_path}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    return OpenProjectResponse(
        project_name=project_path.name,
        project_path=str(project_path),
        tree=tree,
    )


@router.post("/close", response_model=SuccessResponse, summary="Close the current project")
async def close_project():
    """Close the currently open project."""
    workspace_service.close_project()
    return SuccessResponse(message="Project closed.")


@router.get("/recent", summary="List recently opened projects")
async def get_recent():
    """Return the list of recently opened projects (most recent first)."""
    return workspace_service.get_recent_projects()


@router.delete("/recent", response_model=SuccessResponse, summary="Remove a recent project entry")
async def remove_recent(path: str):
    """Remove an entry from the recent-projects list."""
    workspace_service.remove_recent(path)
    return SuccessResponse(message=f"Removed from recents: {path}")
