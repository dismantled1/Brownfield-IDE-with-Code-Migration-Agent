"""
Centralized Configuration System for the AI Provider Layer.

Manages settings persisted in ~/.brownfield-ide/settings.json.
Provides auto-detection of Ollama installation and models.
"""

from __future__ import annotations
import os
import json
import logging
import subprocess
import urllib.request
import socket
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

import platform
if platform.system() == "Windows":
    _SETTINGS_DIR = Path.home() / ".brownfield-ide"
else:
    _SETTINGS_DIR = Path("/tmp/.brownfield-ide")
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "current_provider": "ollama",
    "providers": {
        "ollama": {
            "model": "",
            "base_url": "http://localhost:11434",
            "timeout": 120,
            "temperature": 0.2
        },
        "gemini": {
            "model": "gemini-2.5-flash",
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com",
            "timeout": 45,
            "temperature": 0.2
        },
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "api_key": "",
            "base_url": "https://api.groq.com/openai/v1",
            "timeout": 45,
            "temperature": 0.2
        },
        "openrouter": {
            "model": "openai/gpt-4o-mini",
            "api_key": "",
            "base_url": "https://openrouter.ai/api/v1",
            "timeout": 45,
            "temperature": 0.2
        },
        "openai": {
            "model": "gpt-4o-mini",
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "timeout": 45,
            "temperature": 0.2
        },
        "azure_openai": {
            "model": "gpt-4o-mini",
            "api_key": "",
            "base_url": "",
            "api_version": "2024-02-15-preview",
            "timeout": 45,
            "temperature": 0.2
        },
        "local_api": {
            "model": "custom-model",
            "api_key": "",
            "base_url": "http://localhost:8080/v1",
            "timeout": 45,
            "temperature": 0.2
        }
    }
}


class ConfigManager:
    """Manages AI provider and model configurations."""

    def __init__(self) -> None:
        self._settings: Dict[str, Any] = {}
        self.load_settings()

    def load_settings(self) -> None:
        """Load settings from file, or initialize with defaults if not present."""
        try:
            if _SETTINGS_FILE.exists():
                content = _SETTINGS_FILE.read_text(encoding="utf-8")
                loaded = json.loads(content)
                self._settings = self._merge_defaults(loaded, DEFAULT_SETTINGS)
            else:
                self._settings = json.loads(json.dumps(DEFAULT_SETTINGS))
                self.save_settings()
        except Exception as exc:
            logger.error(f"Error loading AI settings: {exc}")
            self._settings = json.loads(json.dumps(DEFAULT_SETTINGS))

        # Perform startup auto-detection and setup for Ollama
        self._initialize_ollama()

    def _merge_defaults(self, loaded: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge defaults with loaded settings, keeping user modifications."""
        merged = json.loads(json.dumps(defaults))
        if not isinstance(loaded, dict):
            return merged

        # Copy top level values
        for k, v in loaded.items():
            if k != "providers":
                merged[k] = v

        # Copy providers config
        loaded_provs = loaded.get("providers", {})
        if isinstance(loaded_provs, dict):
            for prov_key, prov_val in loaded_provs.items():
                if prov_key in merged["providers"] and isinstance(prov_val, dict):
                    for k, v in prov_val.items():
                        merged["providers"][prov_key][k] = v
                elif isinstance(prov_val, dict):
                    merged["providers"][prov_key] = prov_val

        return merged

    def save_settings(self) -> None:
        """Save current settings to file."""
        try:
            _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            _SETTINGS_FILE.write_text(
                json.dumps(self._settings, indent=2),
                encoding="utf-8"
            )
        except Exception as exc:
            logger.error(f"Error saving AI settings: {exc}")

    def _initialize_ollama(self) -> None:
        """Detect Ollama, list models, and automatically select default if needed."""
        # 1. Detect if Ollama is installed
        installed = self.is_ollama_installed()
        
        # 2. Detect all locally available models
        models = self.detect_ollama_models()

        logger.info(f"Ollama detection: installed={installed}, detected_models={models}")

        # 3. Handle model configuration and auto-selection
        ollama_cfg = self._settings.get("providers", {}).get("ollama", {})
        current_model = ollama_cfg.get("model", "").strip()

        if installed and models:
            # If current model is not configured, or is configured but not installed
            if not current_model or current_model not in models:
                # If "qwen2.5-coder:7b" is present in the list, make it preferred,
                # else choose the first available model.
                preferred = None
                for m in models:
                    if "qwen2.5-coder" in m or "qwen2.5-coder:7b" == m:
                        preferred = m
                        break
                
                selected_model = preferred if preferred else models[0]
                ollama_cfg["model"] = selected_model
                logger.info(f"Ollama auto-selected model: {selected_model}")
                self.save_settings()
        elif not installed or not models:
            # If Ollama is not installed or has no models, we don't clear the config
            # but log a warning.
            logger.warning("Ollama is either not installed/running, or has no local models installed.")

    def is_ollama_installed(self) -> bool:
        """Check if Ollama service is reachable, or command is available."""
        # Check CLI command
        if shutil.which("ollama"):
            return True

        # Check connection to the local Ollama host
        ollama_cfg = self._settings.get("providers", {}).get("ollama", {})
        base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        
        from urllib.parse import urlparse
        try:
            parsed = urlparse(base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 11434
            # Attempt to connect to port
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except Exception:
            pass

        return False

    def detect_ollama_models(self) -> List[str]:
        """Fetch models from local Ollama service or parse from CLI."""
        # Method A: HTTP call to tags endpoint
        ollama_cfg = self._settings.get("providers", {}).get("ollama", {})
        base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        try:
            url = f"{base_url.rstrip('/')}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    return models
        except Exception:
            pass

        # Method B: CLI command "ollama list"
        try:
            res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                models = []
                lines = res.stdout.strip().splitlines()
                if len(lines) > 1:
                    for line in lines[1:]:
                        parts = line.split()
                        if parts:
                            models.append(parts[0])
                return models
        except Exception:
            pass

        return []

    # --- Property Getters ---

    @property
    def current_provider(self) -> str:
        """Active provider key, allowing override via environment variable."""
        forced = os.environ.get("BROWNFIELD_LLM_PROVIDER", "").strip().lower()
        if forced:
            return forced
        return self._settings.get("current_provider", "ollama")

    @current_provider.setter
    def current_provider(self, val: str) -> None:
        self._settings["current_provider"] = val.lower().strip()
        self.save_settings()

    def get_provider_config(self, provider_key: str) -> Dict[str, Any]:
        """Get configuration dictionary for a given provider."""
        return self._settings.get("providers", {}).get(provider_key, {})

    def get_model(self, provider_key: str) -> str:
        """Get the model ID for the provider, with env variable overrides."""
        cfg = self.get_provider_config(provider_key)
        val = cfg.get("model", "")
        
        # Env var override checks
        env_map = {
            "gemini": "GEMINI_MODEL",
            "openai": "OPENAI_MODEL",
            "openrouter": "OPENROUTER_MODEL",
            "ollama": "OLLAMA_MODEL"
        }
        env_var = env_map.get(provider_key)
        if env_var and os.environ.get(env_var):
            return os.environ[env_var]

        # Use defaults if not set
        if not val:
            fallback_models = {
                "gemini": "gemini-2.5-flash",
                "openai": "gpt-4o-mini",
                "openrouter": "openai/gpt-4o-mini",
                "groq": "llama-3.3-70b-versatile",
                "azure_openai": "gpt-4o-mini",
                "local_api": "custom-model",
                "ollama": "qwen2.5-coder:7b"
            }
            return fallback_models.get(provider_key, "")
        return val

    def get_base_url(self, provider_key: str) -> str:
        cfg = self.get_provider_config(provider_key)
        val = cfg.get("base_url", "")
        
        # Env var overrides
        if provider_key == "ollama" and os.environ.get("OLLAMA_HOST"):
            return os.environ["OLLAMA_HOST"]
            
        return val

    def get_api_key(self, provider_key: str) -> Optional[str]:
        cfg = self.get_provider_config(provider_key)
        val = cfg.get("api_key", "").strip()
        if val:
            return val

        # Fallback to env vars
        env_map = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "azure_openai": "AZURE_OPENAI_API_KEY",
            "local_api": "LOCAL_API_KEY"
        }
        env_var = env_map.get(provider_key)
        if env_var:
            return os.environ.get(env_var)
        return None

    def get_timeout(self, provider_key: str) -> int:
        cfg = self.get_provider_config(provider_key)
        return int(cfg.get("timeout", 45))

    def get_temperature(self, provider_key: str) -> float:
        cfg = self.get_provider_config(provider_key)
        return float(cfg.get("temperature", 0.2))

    def get_azure_version(self) -> str:
        cfg = self.get_provider_config("azure_openai")
        return cfg.get("api_version", "2024-02-15-preview")

    def update_settings(self, new_settings: Dict[str, Any]) -> None:
        """Update settings and save to disk."""
        if "current_provider" in new_settings:
            self._settings["current_provider"] = new_settings["current_provider"].strip().lower()

        if "providers" in new_settings:
            for prov_key, prov_val in new_settings["providers"].items():
                if prov_key in self._settings["providers"] and isinstance(prov_val, dict):
                    for k, v in prov_val.items():
                        # Don't overwrite api_key with masked string
                        if k == "api_key" and v.startswith("********"):
                            continue
                        self._settings["providers"][prov_key][k] = v

        self.save_settings()
        # Re-initialize to apply updates
        self._initialize_ollama()

    def get_settings_summary(self) -> Dict[str, Any]:
        """Generate a user-facing summary of the settings, masking keys."""
        summary = {
            "current_provider": self.current_provider,
            "providers": {}
        }
        for prov_key, prov_cfg in self._settings.get("providers", {}).items():
            cfg_copy = dict(prov_cfg)
            # Mask API Key
            key_val = self.get_api_key(prov_key)
            if key_val:
                cfg_copy["api_key"] = "********" + key_val[-4:] if len(key_val) > 4 else "********"
            else:
                cfg_copy["api_key"] = ""
            
            # Make sure active model and base url reflect environment overrides
            cfg_copy["model"] = self.get_model(prov_key)
            cfg_copy["base_url"] = self.get_base_url(prov_key)
            summary["providers"][prov_key] = cfg_copy

        # Include additional runtime diagnostics
        summary["diagnostics"] = {
            "ollama_installed": self.is_ollama_installed(),
            "ollama_models": self.detect_ollama_models()
        }
        return summary


# Singleton instance
config_manager = ConfigManager()
