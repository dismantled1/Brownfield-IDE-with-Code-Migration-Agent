"""
Pluggable LLM provider layer (Phase 5).

Exposes a provider-agnostic interface so the Development Agent never hardcodes
a model vendor. Supported providers: Gemini, OpenRouter, Ollama, OpenAI.
Selection is driven by environment variables (see registry.get_active_provider).
"""

from backend.services.llm.base import LLMProvider, LLMResult
from backend.services.llm.registry import get_active_provider, list_providers

__all__ = [
    "LLMProvider",
    "LLMResult",
    "get_active_provider",
    "list_providers",
]
