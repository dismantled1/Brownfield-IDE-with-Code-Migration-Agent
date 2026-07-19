"""
Extension Point: AI Migration Agent (Phase 3)
=============================================
Thin façade over backend.services.migration_agent_service. Phase 4 (validation),
Phase 5 (apply migration) and Phase 6 (integration) consume the generated code
and the hand-off envelope exposed here.

Nothing in this layer validates, compiles, or applies generated code — the agent
only produces code into an isolated staging workspace. The original project is
never modified.
"""

from typing import Any, Dict, Optional

from backend.models.schemas import MigrationGenerateRequest
from backend.services.migration_agent_service import migration_agent_service


class MigrationAgentLayer:
    """Façade exposing the AI Migration Agent to later phases."""

    def __init__(self) -> None:
        self._service = migration_agent_service

    def generate(self, project_root: str, req: MigrationGenerateRequest) -> None:
        """Start background code generation from the active Migration Plan."""
        self._service.trigger_generation(project_root, req)

    def get_status(self) -> Dict[str, Any]:
        return self._service.get_status().model_dump()

    def get_file(self, generated_path: str) -> Optional[Dict[str, Any]]:
        gen = self._service.get_file(generated_path)
        return gen.model_dump() if gen else None

    # --- Hand-off surface for downstream phases ---------------------------

    def get_handoff(self) -> Optional[Dict[str, Any]]:
        """Return the Phase 4/5/6 hand-off envelope (staging path, files, etc.)."""
        return self._service.get_handoff()

    def get_staging_path(self) -> Optional[str]:
        """Absolute path to the isolated staging workspace for the last run."""
        return self._service.staging_path

    def reset(self) -> None:
        self._service.reset()


# Singleton instance
migration_agent_layer = MigrationAgentLayer()
