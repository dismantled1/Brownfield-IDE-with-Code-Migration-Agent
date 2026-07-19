"""
Concrete LLM providers (Phase 5 redesigned).

All providers use the stdlib (urllib) to avoid third-party dependencies,
and query the ConfigManager to retrieve configured settings (model, keys, etc.).
"""

from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

from backend.services.llm.base import LLMProvider, LLMResult
from backend.services.llm.config import config_manager

logger = logging.getLogger(__name__)


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    key = "gemini"

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt, system=None, temperature=None, timeout=None) -> LLMResult:
        api_key = self.api_key
        if not api_key:
            return LLMResult("", self.key, self.model, ok=False, error="missing GEMINI_API_KEY")
        
        base_url = self.base_url or "https://generativelanguage.googleapis.com"
        url = (
            f"{base_url.rstrip('/')}/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        
        temp = temperature if temperature is not None else self.temperature
        to = timeout if timeout is not None else self.timeout
        
        parts = []
        if system:
            parts.append({"text": system})
        parts.append({"text": prompt})
        
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": temp},
        }
        try:
            data = _http_post_json(url, payload, {}, to)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return LLMResult(text, self.key, self.model)
        except Exception as exc:
            logger.error(f"Gemini generate failed: {exc}")
            return LLMResult("", self.key, self.model, ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# OpenAI-compatible base (OpenAI, OpenRouter, Groq, Local APIs)
# ---------------------------------------------------------------------------

class _OpenAICompatProvider(LLMProvider):
    """Shared logic for OpenAI Chat Completions compatible providers."""

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _extra_headers(self) -> dict:
        return {}

    def generate(self, prompt, system=None, temperature=None, timeout=None) -> LLMResult:
        api_key = self.api_key
        if not api_key and self.key != "local_api":
            # For non-local APIs, require an API key
            return LLMResult("", self.key, self.model, ok=False, error=f"missing API key for {self.key}")
        
        if not self.base_url:
            return LLMResult("", self.key, self.model, ok=False, error=f"missing base_url for {self.key}")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        
        temp = temperature if temperature is not None else self.temperature
        to = timeout if timeout is not None else self.timeout
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "temperature": temp}
        
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers.update(self._extra_headers())
        
        try:
            data = _http_post_json(url, payload, headers, to)
            text = data["choices"][0]["message"]["content"]
            return LLMResult(text, self.key, self.model)
        except Exception as exc:
            logger.error(f"{self.key} generate failed: {exc}")
            return LLMResult("", self.key, self.model, ok=False, error=str(exc))


class OpenAIProvider(_OpenAICompatProvider):
    key = "openai"


class OpenRouterProvider(_OpenAICompatProvider):
    key = "openrouter"

    def _extra_headers(self) -> dict:
        return {
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Brownfield IDE",
        }


class GroqProvider(_OpenAICompatProvider):
    key = "groq"


class LocalAPIProvider(_OpenAICompatProvider):
    key = "local_api"

    def available(self) -> bool:
        # Local API is available if its base URL is set
        return bool(self.base_url)


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

class AzureOpenAIProvider(LLMProvider):
    key = "azure_openai"

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def generate(self, prompt, system=None, temperature=None, timeout=None) -> LLMResult:
        api_key = self.api_key
        if not api_key:
            return LLMResult("", self.key, self.model, ok=False, error="missing Azure API key")
        if not self.base_url:
            return LLMResult("", self.key, self.model, ok=False, error="missing Azure base_url")
            
        temp = temperature if temperature is not None else self.temperature
        to = timeout if timeout is not None else self.timeout
        api_version = config_manager.get_azure_version()
        
        url = f"{self.base_url.rstrip('/')}/openai/deployments/{self.model}/chat/completions?api-version={api_version}"
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"messages": messages, "temperature": temp}
        headers = {
            "api-key": api_key,
        }
        try:
            data = _http_post_json(url, payload, headers, to)
            text = data["choices"][0]["message"]["content"]
            return LLMResult(text, self.key, self.model)
        except Exception as exc:
            logger.error(f"Azure OpenAI generate failed: {exc}")
            return LLMResult("", self.key, self.model, ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Ollama (local LLMs)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    key = "ollama"

    def available(self) -> bool:
        return config_manager.is_ollama_installed()

    def generate(self, prompt, system=None, temperature=None, timeout=None) -> LLMResult:
        host = self.base_url or "http://localhost:11434"
        url = f"{host.rstrip('/')}/api/chat"
        
        temp = temperature if temperature is not None else self.temperature
        to = timeout if timeout is not None else self.timeout
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temp},
        }
        try:
            data = _http_post_json(url, payload, {}, to)
            text = data.get("message", {}).get("content", "")
            if not text:
                return LLMResult("", self.key, self.model, ok=False, error="empty response")
            return LLMResult(text, self.key, self.model)
        except Exception as exc:
            logger.error(f"Ollama generate failed: {exc}")
            return LLMResult("", self.key, self.model, ok=False, error=str(exc))


# Registry list of all supported providers.
ALL_PROVIDERS = [
    OllamaProvider(),
    GeminiProvider(),
    GroqProvider(),
    OpenRouterProvider(),
    OpenAIProvider(),
    AzureOpenAIProvider(),
    LocalAPIProvider(),
]
