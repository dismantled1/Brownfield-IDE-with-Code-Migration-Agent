"""
Extension Point: Validation Layer
=====================================
Phase 6 Integration Point — now wired to backend.services.validation_service.

Validates proposed (not-yet-applied) code changes by running syntax, static
analysis, dependency, test, and change-impact checks, then records the user's
approval decision. Nothing here modifies project source files — application
happens in Phase 7 (Source Update Engine).
"""

from typing import Dict, Any, Optional

from backend.services.validation_service import validation_service


class ValidationLayer:
    """Thin façade over the Validation & Approval engine (singleton service)."""

    def __init__(self):
        self._service = validation_service

    def validate_changes(self, project_root: str, plan_id: str,
                         force: bool = False) -> Dict[str, Any]:
        """Run all validation checks on a proposed change bundle (by plan_id)."""
        return self._service.validate(plan_id, project_root, force=force)

    def get_report(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._service.get_report(plan_id)

    def approve(self, plan_id: str) -> Dict[str, Any]:
        """Record approval (stores state only — no file writes)."""
        return self._service.approve(plan_id)

    def reject(self, plan_id: str) -> Dict[str, Any]:
        """Record rejection (discards the proposal)."""
        return self._service.reject(plan_id)

    def get_decision(self, plan_id: str) -> Dict[str, Any]:
        return self._service.get_decision(plan_id)


# Singleton instance
validation_layer = ValidationLayer()
