"""
Extension Point: Migration Validation & Approval (Phase 4)
==========================================================
Thin façade over backend.services.migration_validation_service. Phase 5 (Apply
Migration) consumes the approval output exposed here.

This layer never modifies, compiles, applies, exports, or deletes anything — it
only validates generated code and records approval decisions.
"""

from typing import Any, Dict, Optional

from backend.services.migration_validation_service import migration_validation_service


class MigrationValidationLayer:
    """Façade exposing validation + approval to later phases."""

    def __init__(self) -> None:
        self._service = migration_validation_service

    def validate(self) -> None:
        """Start background validation of the current generation session."""
        self._service.trigger_validation()

    def get_status(self) -> Dict[str, Any]:
        return self._service.get_status().model_dump()

    def get_file_result(self, generated_path: str) -> Optional[Dict[str, Any]]:
        return self._service.get_file_result(generated_path)

    # --- Approval workflow ------------------------------------------------

    def approve_file(self, generated_path: str) -> Dict[str, Any]:
        return self._service.approve_file(generated_path)

    def reject_file(self, generated_path: str) -> Dict[str, Any]:
        return self._service.reject_file(generated_path)

    def approve_all_safe(self) -> Dict[str, Any]:
        return self._service.approve_all_safe()

    def reject_migration(self) -> Dict[str, Any]:
        return self._service.reject_migration()

    # --- Phase 5 hand-off -------------------------------------------------

    def get_approval_output(self) -> Dict[str, Any]:
        """Approved / rejected / pending file lists + validation metadata."""
        return self._service.get_approval_output().model_dump()

    def reset(self) -> None:
        self._service.reset()


# Singleton instance
migration_validation_layer = MigrationValidationLayer()
