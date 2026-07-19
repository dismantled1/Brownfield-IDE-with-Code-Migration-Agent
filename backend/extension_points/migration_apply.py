"""
Extension Point: Migration Application (Phase 5)
================================================
Thin façade over backend.services.migration_apply_service. Phase 6 (Final
Integration & E2E Verification) can consume the migration history, final report,
and rollback surface exposed here.

Applies approved code with backups and full rollback. Consumes prior-phase output
only — it never regenerates, re-analyzes, or re-validates.
"""

from typing import Any, Dict, List, Optional

from backend.services.migration_apply_service import migration_apply_service


class MigrationApplyLayer:
    """Façade exposing apply / rollback / history to later phases."""

    def __init__(self) -> None:
        self._service = migration_apply_service

    def preview(self) -> Dict[str, Any]:
        return self._service.build_change_set().model_dump()

    def apply(self, applied_by: Optional[str] = None) -> Dict[str, Any]:
        return self._service.apply(applied_by=applied_by).model_dump()

    def rollback(self, migration_id: str, file: Optional[str] = None) -> Dict[str, Any]:
        return self._service.rollback(migration_id, file=file)

    def history(self) -> List[Dict[str, Any]]:
        return [r.model_dump() for r in self._service.get_history()]

    def last_report(self) -> Optional[Dict[str, Any]]:
        rep = self._service.get_last_report()
        return rep.model_dump() if rep else None


# Singleton instance
migration_apply_layer = MigrationApplyLayer()
