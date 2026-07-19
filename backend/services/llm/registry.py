"""
Provider registry / selection (Phase 5 redesigned).

Selection is driven by config_manager.current_provider (which supports
both settings.json and environment overrides).
"""

from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any

from backend.services.llm.base import LLMProvider
from backend.services.llm.providers import ALL_PROVIDERS
from backend.services.llm.config import config_manager

logger = logging.getLogger(__name__)


def _by_key() -> Dict[str, LLMProvider]:
    return {p.key: p for p in ALL_PROVIDERS}


def get_active_provider() -> Optional[LLMProvider]:
    """Return the provider to use based on configuration, or None for offline mode."""
    active_key = config_manager.current_provider
    providers = _by_key()
    provider = providers.get(active_key)

    if provider and provider.available():
        return provider

    logger.warning(
        f"Configured LLM provider '{active_key}' is not available/configured. "
        f"Falling back to first available."
    )

    # Fallback search order
    for p in ALL_PROVIDERS:
        if p.available():
            return p

    return None


def list_providers() -> List[Dict[str, Any]]:
    """Describe all providers and their availability (for the UI / diagnostics)."""
    active = get_active_provider()
    active_key = active.key if active else None
    return [
        {
            "key": p.key,
            "model": p.model,
            "available": p.available(),
            "active": p.key == active_key,
        }
        for p in ALL_PROVIDERS
    ]
