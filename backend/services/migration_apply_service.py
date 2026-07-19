"""
Migration Application Engine — Phase 5
======================================
Applies APPROVED migrated code into the original project safely, and supports
full/partial rollback. It consumes outputs from earlier phases only — it never
regenerates code, re-runs analysis, or re-runs validation.

Safety model (no data loss):
  * Every file that will be replaced/modified/deleted is copied to a per-migration
    backup workspace BEFORE anything is written.
  * Only approved files are applied. Rejected / pending / failed files are skipped.
  * Each application creates a migration record (id, timestamp, backup location,
    per-file changes) persisted to disk, enabling rollback after restarts.
  * Rollback restores replaced/deleted originals from the backup and removes files
    that were newly created.

This is the one phase that intentionally writes to the original project — always
gated by explicit approval (Phase 4) and always reversible.
"""

from __future__ import annotations

import os
import json
import time
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.models.schemas import (
    ChangeSet,
    ChangeSetItem,
    MigrationRecord,
    FinalReport,
)
from backend.services.migration_service import migration_service
from backend.services.migration_agent_service import migration_agent_service
from backend.services.migration_validation_service import migration_validation_service

logger = logging.getLogger(__name__)

_BASE = Path.home() / ".brownfield-ide"
_BACKUP_ROOT = _BASE / "backups"
_HISTORY_FILE = _BASE / "migration_history.json"


class MigrationApplyError(Exception):
    """Recoverable, user-facing apply/rollback error."""


class MigrationApplyService:
    """Applies approved migration output and manages backups + rollback."""

    def __init__(self) -> None:
        self._history: List[MigrationRecord] = []
        self._last_report: Optional[FinalReport] = None
        self._load_history()

    # ------------------------------------------------------------------
    # Change set (preview) — consumes Phase 4 approval output
    # ------------------------------------------------------------------

    def build_change_set(self) -> ChangeSet:
        approval = migration_validation_service.get_approval_output()
        plan = migration_service.active_plan
        project_root = plan.project_path if plan else None

        cs = ChangeSet(
            project_root=project_root,
            target_language=(plan.target_language if plan else None),
            total_approved=len(approval.approved_files),
        )

        # Skipped = rejected + pending (never applied).
        for f in approval.rejected_files:
            cs.skipped.append({**f, "reason": "rejected"})
        for f in approval.pending_review_files:
            cs.skipped.append({**f, "reason": f.get("reason", "pending review")})

        if not project_root:
            cs.ready = False
            cs.message = "No migration plan / project root available."
            return cs
        if not approval.approved_files:
            cs.ready = False
            cs.message = "No approved files. Validate (Phase 4) and approve files first."
            return cs

        root = Path(project_root).resolve()
        for entry in approval.approved_files:
            gen_path = entry.get("generated_path")
            gf = migration_agent_service.get_file(gen_path) if gen_path else None
            if not gf:
                cs.skipped.append({**entry, "reason": "generated file not found"})
                continue

            target_path = gf.generated_path
            target_abs = (root / target_path)
            exists = target_abs.exists()

            if gf.generation_status if hasattr(gf, "generation_status") else False:
                pass  # (GeneratedFile has 'status', handled below)

            gstatus = getattr(gf, "status", "new")
            if gstatus == "modified" and exists:
                mode = "modify"
            elif exists:
                mode = "replace"
            else:
                mode = "create"

            item = ChangeSetItem(
                generated_path=gf.generated_path,
                original_path=gf.original_path,
                target_path=target_path,
                mode=mode,
                component_type=gf.component_type,
                language=gf.language,
                exists=exists,
                additions=gf.additions,
                removals=gf.removals,
            )
            if mode == "create":
                cs.to_create.append(item)
            elif mode == "modify":
                cs.to_modify.append(item)
            elif mode == "replace":
                cs.to_replace.append(item)
            elif mode == "delete":
                cs.to_delete.append(item)
            elif mode == "rename":
                cs.to_rename.append(item)

        cs.ready = bool(cs.to_create or cs.to_replace or cs.to_modify or cs.to_delete or cs.to_rename)
        if not cs.ready:
            cs.message = "Nothing to apply."
        return cs

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, applied_by: Optional[str] = None) -> FinalReport:
        started = time.time()
        cs = self.build_change_set()
        if not cs.ready:
            raise MigrationApplyError(cs.message or "Nothing to apply.")

        project_root = Path(cs.project_root).resolve()
        migration_id = uuid.uuid4().hex[:12]
        backup_dir = _BACKUP_ROOT / migration_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        all_items = (cs.to_create + cs.to_modify + cs.to_replace + cs.to_rename + cs.to_delete)
        changes_record: List[Dict[str, Any]] = []
        created = replaced = deleted = modified = failed = 0
        applied_files: List[str] = []

        for item in all_items:
            try:
                target_abs = (project_root / item.target_path).resolve()
                # Path-traversal guard — never write outside the project.
                target_abs.relative_to(project_root)

                pre_existed = target_abs.exists()
                backup_rel: Optional[str] = None

                # Back up the original before any destructive change.
                if pre_existed and item.mode in ("replace", "modify", "delete", "rename"):
                    backup_rel = self._backup_file(target_abs, item.target_path, backup_dir)

                if item.mode == "delete":
                    if pre_existed:
                        target_abs.unlink()
                        deleted += 1
                else:
                    # create / replace / modify / rename → write generated content.
                    gf = migration_agent_service.get_file(item.generated_path)
                    content = gf.generated_content if gf else ""
                    target_abs.parent.mkdir(parents=True, exist_ok=True)
                    target_abs.write_text(content, encoding="utf-8")
                    if item.mode == "create":
                        created += 1
                    elif item.mode == "modify":
                        modified += 1
                    else:
                        replaced += 1

                    # rename → remove the original source after writing the new file.
                    if item.mode == "rename" and item.original_path and item.original_path != item.target_path:
                        orig_abs = (project_root / item.original_path).resolve()
                        if orig_abs.exists():
                            self._backup_file(orig_abs, item.original_path, backup_dir)
                            orig_abs.unlink()

                applied_files.append(item.target_path)
                changes_record.append({
                    "target_path": item.target_path,
                    "generated_path": item.generated_path,
                    "original_path": item.original_path,
                    "mode": item.mode,
                    "pre_existed": pre_existed,
                    "backup_path": backup_rel,
                    "status": "applied",
                })
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.error(f"Apply failed for {item.target_path}: {exc}", exc_info=True)
                changes_record.append({
                    "target_path": item.target_path,
                    "generated_path": item.generated_path,
                    "mode": item.mode,
                    "status": "failed",
                    "error": str(exc),
                })

        duration_ms = round((time.time() - started) * 1000, 1)
        plan = migration_service.active_plan
        approval = migration_validation_service.get_approval_output()
        validation_score = approval.validation_metadata.get("validation_score")

        record = MigrationRecord(
            migration_id=migration_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_root=str(project_root),
            target_language=cs.target_language,
            applied_by=applied_by or "local user",
            files_applied=len(applied_files),
            files_created=created,
            files_replaced=replaced + modified,
            files_deleted=deleted,
            files_skipped=len(cs.skipped),
            backup_location=str(backup_dir),
            duration_ms=duration_ms,
            validation_score=validation_score,
            rollback_available=True,
            changes=changes_record,
        )
        self._history.append(record)
        self._save_history()
        self._write_manifest(backup_dir, record)

        # Post-application: refresh IDE indexes/caches (best-effort).
        self._refresh_workspace(str(project_root))

        report = self._build_report(cs, record, created, replaced, modified, deleted, failed)
        self._last_report = report
        return report

    def _backup_file(self, src_abs: Path, rel_path: str, backup_dir: Path) -> str:
        """Copy an original file into the migration backup, preserving structure."""
        dest = backup_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_abs, dest)
        return rel_path

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, migration_id: str, file: Optional[str] = None) -> Dict[str, Any]:
        record = self._find_record(migration_id)
        if not record:
            raise MigrationApplyError(f"Migration '{migration_id}' not found in history.")
        if record.rolled_back and not file:
            return {"success": False, "message": "Migration already fully rolled back.",
                    "migration_id": migration_id}

        project_root = Path(record.project_root)
        backup_dir = Path(record.backup_location)
        restored = removed = 0
        target_filter = (file or "").replace("\\", "/").strip("/") or None

        # Reverse order so renames/creates unwind cleanly.
        for change in reversed(record.changes):
            if change.get("status") != "applied":
                continue
            if change.get("reverted"):
                continue
            tpath = change["target_path"]
            if target_filter and tpath != target_filter:
                continue

            target_abs = (project_root / tpath)
            mode = change["mode"]
            pre_existed = change.get("pre_existed", False)
            backup_path = change.get("backup_path")

            try:
                if mode == "create":
                    # Newly created → delete it to restore original state.
                    if target_abs.exists():
                        target_abs.unlink()
                        removed += 1
                elif mode in ("replace", "modify", "delete", "rename"):
                    if backup_path:
                        src = backup_dir / backup_path
                        if src.exists():
                            target_abs.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src, target_abs)
                            restored += 1
                    # rename also re-created a new target file → remove it if it was new.
                    if mode == "rename" and not pre_existed and target_abs.exists():
                        target_abs.unlink()
                        removed += 1
                change["reverted"] = True
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Rollback failed for {tpath}: {exc}", exc_info=True)

        if not target_filter:
            record.rollback_available = False
            record.rolled_back = True
            record.rolled_back_at = datetime.now(timezone.utc).isoformat()
        self._save_history()
        self._write_manifest(backup_dir, record)
        self._refresh_workspace(record.project_root)

        return {
            "success": True,
            "migration_id": migration_id,
            "restored": restored,
            "removed": removed,
            "scope": "file" if target_filter else "migration",
            "message": (f"Restored file '{target_filter}'." if target_filter
                        else f"Rolled back migration {migration_id}: {restored} restored, {removed} removed."),
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self) -> List[MigrationRecord]:
        return list(reversed(self._history))  # newest first

    def get_last_report(self) -> Optional[FinalReport]:
        return self._last_report

    # ------------------------------------------------------------------
    # Post-application workspace refresh (best-effort, never fatal)
    # ------------------------------------------------------------------

    def _refresh_workspace(self, project_root: str) -> None:
        # Search index
        try:
            from backend.services.search_service import search_service
            search_service.build_index(project_root)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Search refresh skipped: {exc}")
        # Impact graph — force rebuild on next access
        try:
            from backend.services.impact_service import impact_service
            impact_service._last_analyzed_at = ""
            impact_service.file_dependents = {}
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Impact refresh skipped: {exc}")
        # Migration analysis cache (Phase 2) — clear so it re-scans new files
        try:
            migration_service._cache.clear()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Migration cache clear skipped: {exc}")
        # Project analysis / file metadata — trigger a background rescan
        try:
            from backend.services.analysis_service import analysis_manager
            analysis_manager.trigger_analysis(project_root)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Analysis refresh skipped: {exc}")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _build_report(self, cs: ChangeSet, record: MigrationRecord,
                      created: int, replaced: int, modified: int,
                      deleted: int, failed: int) -> FinalReport:
        new_files = [c["target_path"] for c in record.changes
                     if c.get("status") == "applied" and c["mode"] == "create"]
        modified_files = [c["target_path"] for c in record.changes
                          if c.get("status") == "applied" and c["mode"] in ("replace", "modify")]
        deleted_files = [c["target_path"] for c in record.changes
                         if c.get("status") == "applied" and c["mode"] == "delete"]
        applied_files = [c["target_path"] for c in record.changes if c.get("status") == "applied"]
        skipped_files = [s.get("generated_path") or s.get("original_path") or "?" for s in cs.skipped]

        summary = {
            "files_applied": record.files_applied,
            "files_created": created,
            "files_modified": replaced + modified,
            "files_deleted": deleted,
            "files_failed": failed,
            "files_skipped": len(cs.skipped),
            "validation_score": record.validation_score,
        }
        report = FinalReport(
            success=(failed == 0),
            migration_id=record.migration_id,
            project_root=record.project_root,
            target_language=record.target_language,
            applied_files=applied_files,
            skipped_files=skipped_files,
            modified_files=modified_files,
            new_files=new_files,
            deleted_files=deleted_files,
            backup_location=record.backup_location,
            rollback_status="available",
            duration_ms=record.duration_ms,
            summary=summary,
        )
        report.report_markdown = self._report_markdown(report, record)
        return report

    @staticmethod
    def _report_markdown(r: FinalReport, rec: MigrationRecord) -> str:
        return f"""
# MIGRATION APPLICATION REPORT

**Migration ID:** `{r.migration_id}`
**Applied:** {rec.timestamp}  |  **By:** {rec.applied_by}
**Target Language:** {r.target_language}
**Duration:** {r.duration_ms} ms

---

## Result
- **New Files:** {len(r.new_files)}
- **Modified / Replaced Files:** {len(r.modified_files)}
- **Deleted Files:** {len(r.deleted_files)}
- **Skipped (rejected/pending):** {len(r.skipped_files)}
- **Applied Total:** {len(r.applied_files)}

## Backup & Rollback
- **Backup Location:** `{r.backup_location}`
- **Rollback:** {r.rollback_status} (use migration id `{r.migration_id}`)

---
> Original files were backed up before changes. This migration can be fully rolled back.
""".strip()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        try:
            if _HISTORY_FILE.exists():
                data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
                self._history = [MigrationRecord(**r) for r in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not load migration history: {exc}")
            self._history = []

    def _save_history(self) -> None:
        try:
            _BASE.mkdir(parents=True, exist_ok=True)
            _HISTORY_FILE.write_text(
                json.dumps([r.model_dump() for r in self._history], indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Could not save migration history: {exc}")

    def _write_manifest(self, backup_dir: Path, record: MigrationRecord) -> None:
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / "manifest.json").write_text(
                json.dumps(record.model_dump(), indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Manifest write skipped: {exc}")

    def _find_record(self, migration_id: str) -> Optional[MigrationRecord]:
        for r in self._history:
            if r.migration_id == migration_id:
                return r
        return None


# Global singleton instance
migration_apply_service = MigrationApplyService()
