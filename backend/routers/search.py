import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any

from backend.services.search_service import search_service
from backend.routers.filesystem import get_project_root

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("", summary="Search files, symbols, and endpoints by natural language or keywords")
async def query_search(
    q: str = Query(..., min_length=1, description="Search query"),
    project_root: str = Depends(get_project_root)
):
    """
    Performs full-text code search, symbol lookup, and regex endpoint matching.
    Optionally re-ranks results using LLM models when API keys are configured.
    """
    try:
        results = search_service.search(q, project_root)
        return results
    except Exception as exc:
        logger.error(f"Search query failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/references", summary="Trace references and dependencies for a symbol")
async def query_references(
    symbol: str = Query(..., min_length=1, description="Class name, function name, or filepath"),
    project_root: str = Depends(get_project_root)
):
    """
    Returns lists of incoming references (usages of this symbol across the project)
    and outgoing references (superclasses or dependencies).
    """
    try:
        references = search_service.find_references(symbol, project_root)
        return references
    except Exception as exc:
        logger.error(f"References scan failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
