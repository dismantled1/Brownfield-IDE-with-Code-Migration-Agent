"""
LLM provider interface (Phase 5).

A provider is a thin adapter that turns a (system, prompt) pair into text.
Implementations live in providers.py. The agent depends only on this interface,
keeping model vendors fully pluggable.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from backend.services.llm.config import config_manager


@dataclass
class LLMResult:
    """Outcome of a generation call."""
    text: str
    provider: str
    model: str
    ok: bool = True
    error: Optional[str] = None


class LLMProvider(ABC):
    """Abstract base for all model providers."""

    #: short identifier, e.g. "gemini", "ollama"
    key: str = "base"

    @property
    def model(self) -> str:
        """The model id this provider will call."""
        return config_manager.get_model(self.key)

    @property
    def base_url(self) -> str:
        """The base URL for the API endpoint."""
        return config_manager.get_base_url(self.key)

    @property
    def api_key(self) -> Optional[str]:
        """The API key for the provider."""
        return config_manager.get_api_key(self.key)

    @property
    def timeout(self) -> int:
        """Default timeout in seconds."""
        return config_manager.get_timeout(self.key)

    @property
    def temperature(self) -> float:
        """Default temperature setting."""
        return config_manager.get_temperature(self.key)

    @abstractmethod
    def available(self) -> bool:
        """True when the provider is configured and available."""
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
    ) -> LLMResult:
        """Generate a completion. Implementations must not raise — return an
        LLMResult with ok=False on failure so callers can fall back gracefully."""
        raise NotImplementedError
