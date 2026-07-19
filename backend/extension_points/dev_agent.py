"""
Extension Point: Development Agent
=====================================
Phase 5 Integration Point — now wired to backend.services.agent_service.

Hosts the AI-powered Development Agent that turns natural-language requests into
*proposed* modifications (plan + generated code + diffs + validation). It never
writes to project files; outputs feed Phase 6 (validation/approval) and Phase 7
(source update).
"""

from typing import Dict, Any, Optional

from backend.services.agent_service import agent_service


class DevAgent:
    """Thin façade over the Development Agent engine (singleton service)."""

    def __init__(self):
        self._service = agent_service

    def develop(self, project_root: str, request: str) -> Dict[str, Any]:
        """Generate a full proposed-change bundle for a request."""
        return self._service.develop(request, project_root)

    def implement_feature(self, project_root: str, request: str,
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Feature-enhancement entry point (delegates to the unified engine)."""
        return self._service.develop(request, project_root)

    def fix_bug(self, project_root: str, bug_description: str,
                file_path: Optional[str] = None) -> Dict[str, Any]:
        """Bug-fix entry point."""
        return self._service.develop(bug_description, project_root)

    def refactor(self, project_root: str, refactor_type: str, target: str,
                 options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Refactoring entry point."""
        request = f"Refactor {target} ({refactor_type})" if refactor_type else f"Refactor {target}"
        return self._service.develop(request, project_root)

    def get_result(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._service.get_result(plan_id)


# Singleton instance
dev_agent = DevAgent()
