"""
Filesystem Router — REST endpoints for all file/folder operations.
"""

import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from fastapi.responses import JSONResponse

from backend.models.schemas import (
    FileNode,
    FileContent,
    WriteFileRequest,
    CreateFileRequest,
    CreateFolderRequest,
    DeleteRequest,
    RenameRequest,
    SearchResult,
    SuccessResponse,
)
from backend.services import file_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Max ZIP upload size: 1 GB
MAX_ZIP_SIZE = 1 * 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# Dependency: require an open project
# ---------------------------------------------------------------------------

def get_project_root() -> str:
    root = workspace_service.get_current_project()
    if not root:
        raise HTTPException(status_code=400, detail="No project is currently open.")
    if not Path(root).exists():
        raise HTTPException(status_code=404, detail=f"Project path not found: {root}")
    return root


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tree", response_model=FileNode, summary="Get shallow project tree")
async def get_tree(
    depth: int = Query(default=1, ge=1, le=5, description="Tree depth (default 1 for lazy loading)"),
    project_root: str = Depends(get_project_root),
):
    """
    Return the project file tree at the given depth.
    Default depth=1 gives you only root children (folders have children=null
    until the user expands them, triggering /children).
    """
    try:
        tree = file_service.get_tree(project_root, depth=depth)
        return tree
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/children", response_model=list, summary="Get children of a directory (lazy load)")
async def get_children(
    path: str = Query(..., description="Relative path to the directory"),
    project_root: str = Depends(get_project_root),
):
    """
    Return one level of children for a specific directory.
    Called when the user expands a folder in the explorer.
    Each returned folder has children=null (not yet loaded).
    """
    try:
        children = file_service.get_children(project_root, path)
        return [c.model_dump() for c in children]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/file", response_model=FileContent, summary="Read file content")
async def read_file(
    path: str = Query(..., description="Relative path to the file"),
    project_root: str = Depends(get_project_root),
):
    """
    Read and return the content of a text file.
    Binary files and files larger than 10 MB are rejected.
    """
    try:
        result = await file_service.read_file(project_root, path)
        return FileContent(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/file", response_model=SuccessResponse, summary="Save file content")
async def write_file(
    body: WriteFileRequest,
    project_root: str = Depends(get_project_root),
):
    """Save (overwrite) a file with the given content."""
    try:
        await file_service.write_file(project_root, body.path, body.content)
        return SuccessResponse(message=f"Saved: {body.path}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/file", response_model=FileNode, summary="Create a new file")
async def create_file(
    body: CreateFileRequest,
    project_root: str = Depends(get_project_root),
):
    """Create a new empty file."""
    try:
        node = file_service.create_file(project_root, body.path)
        return node
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/folder", response_model=FileNode, summary="Create a new folder")
async def create_folder(
    body: CreateFolderRequest,
    project_root: str = Depends(get_project_root),
):
    """Create a new folder (and any missing parent directories)."""
    try:
        node = file_service.create_folder(project_root, body.path)
        return node
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/item", response_model=SuccessResponse, summary="Delete file or folder")
async def delete_item(
    path: str = Query(..., description="Relative path to the item"),
    project_root: str = Depends(get_project_root),
):
    """Delete a file or folder (folders are deleted recursively)."""
    try:
        file_service.delete_item(project_root, path)
        return SuccessResponse(message=f"Deleted: {path}")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/rename", response_model=FileNode, summary="Rename file or folder")
async def rename_item(
    body: RenameRequest,
    project_root: str = Depends(get_project_root),
):
    """Rename a file or folder within the same directory."""
    try:
        node = file_service.rename_item(project_root, body.path, body.new_name)
        return node
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/search", response_model=SearchResult, summary="Search files by name")
async def search_files(
    q: str = Query(..., min_length=1, description="Search query"),
    max_results: int = Query(default=100, ge=1, le=500),
    project_root: str = Depends(get_project_root),
):
    """Search for files and folders whose names contain the query string."""
    try:
        nodes = file_service.search_files(project_root, q, max_results)
        return SearchResult(nodes=nodes, total=len(nodes), query=q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/upload-zip", summary="Upload and extract a ZIP project")
async def upload_zip(
    file: UploadFile = File(...),
    destination: Optional[str] = Query(default=None, description="Absolute extraction path"),
):
    """
    Upload a ZIP file (max 1 GB) and extract it as a new project.
    After extraction the project is automatically opened.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    # Stream upload to a temp file to avoid memory exhaustion
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name
        total_bytes = 0
        chunk_size = 1024 * 1024  # 1 MB chunks
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_ZIP_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"ZIP file exceeds the 1 GB limit.",
                    )
                tmp.write(chunk)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    # Extract
    try:
        project_path = await file_service.extract_zip(tmp_path, destination)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # Auto-open the extracted project
    workspace_service.open_project(project_path)
    tree = file_service.get_tree(project_path, depth=1)

    return {
        "project_name": Path(project_path).name,
        "project_path": project_path,
        "tree": tree.model_dump(),
        "size_bytes": total_bytes,
    }
