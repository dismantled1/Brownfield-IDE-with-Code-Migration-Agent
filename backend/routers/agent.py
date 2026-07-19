"""
Agent Router (Phase 5) — Development Agent endpoints.

  POST /api/agent/develop          generate a proposed-change bundle
  GET  /api/agent/result/{plan_id} re-fetch a previously generated bundle
  GET  /api/agent/providers        list LLM providers and which is active

The agent only PROPOSES changes; nothing here writes to project files.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.services.agent_service import agent_service
from backend.routers.filesystem import get_project_root
from backend.services.llm.config import config_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class DevelopRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Natural-language dev request")


@router.post("/develop", summary="Generate a proposed change set for a dev request")
async def develop(body: DevelopRequest, project_root: str = Depends(get_project_root)):
    """
    Understand the request, select context, plan changes, generate code,
    produce diffs, and validate — without modifying any source files.
    """
    try:
        return agent_service.develop(body.request, project_root)
    except Exception as exc:
        logger.error(f"Agent develop failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/result/{plan_id}", summary="Fetch a previously generated change set")
async def get_result(plan_id: str):
    bundle = agent_service.get_result(plan_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"No result for plan_id: {plan_id}")
    return bundle


@router.get("/providers", summary="List available LLM providers")
async def providers():
    return {"providers": agent_service.providers()}


@router.get("/settings", summary="Get central AI configuration settings")
async def get_settings():
    try:
        return config_manager.get_settings_summary()
    except Exception as exc:
        logger.error(f"Failed to retrieve settings: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


class SettingsUpdateRequest(BaseModel):
    current_provider: Optional[str] = Field(None, description="The LLM provider key (e.g. ollama, gemini)")
    providers: Optional[Dict[str, Any]] = Field(None, description="Dict of provider configs to update")


@router.post("/settings", summary="Update central AI configuration settings")
async def update_settings(body: SettingsUpdateRequest):
    try:
        config_manager.update_settings(body.model_dump(exclude_none=True))
        return {"success": True, "settings": config_manager.get_settings_summary()}
    except Exception as exc:
        logger.error(f"Failed to update settings: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
