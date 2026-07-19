"""
Source Update Engine (Phase 7).

The final step of the workflow — the ONLY component that writes to real project
files. It applies a change bundle (Phase 5) that has been validated (Phase 6)
and approved by the user, using a transactional model:

    verify approval/drift → backup → apply → verify → commit
                                              └─ on failure: rollback

Provides change history, undo / rollback (restore from backup), and optional
Git integration. State (history + backups) persists under ~/.brownfield-ide so
operations survive restarts.
"""

from __future__ import annotations
import os
import json
import shutil
import hashlib
import logging
import subprocess
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.services.agent_service import agent_service
from backend.services.validation_service import validation_service

logger = logging.getLogger(__name__)

_STATE_ROOT = Path.home() / ".brownfield-ide"
_HISTORY_DIR = _STATE_ROOT / "history"
_BACKUP_ROOT = _STATE_ROOT / "backups"
MAX_HISTORY = 100


class SourceUpdateEngine:
    """Applies approved changes transactionally and manages history/rollback."""

    def __init__(self):
        self.project_path = ""

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, plan_id: str, project_root: str, do_commit: bool = False) -> Dict[str, Any]:
        """Apply an approved, validated change bundle to disk transactionally."""
        self.project_path = str(Path(project_root).resolve())
        root = Path(self.project_path)

        bundle = agent_service.get_result(plan_id)
        if not bundle:
            raise KeyError(f"No proposed-change bundle for plan_id: {plan_id}")

        # --- Approval verification -------------------------------------
        report = validation_service.get_report(plan_id)
        decision = validation_service.get_decision(plan_id)
        if not report:
            return self._blocked("Changes must be validated before they can be applied.")
        if report.get("validation_status") != "PASSED":
            return self._blocked("Validation did not pass — resolve issues and regenerate.")
        if decision.get("state") != "approved":
            return self._blocked("Changes have not been approved.")

        patches = bundle.get("patches", [])
        if not patches:
            return self._blocked("There are no changes to apply.")

        # --- Drift / existence verification ----------------------------
        problems = self._verify_disk_state(root, patches)
        if problems:
            return {
                "status": "NEEDS_REGENERATE",
                "plan_id": plan_id,
                "problems": problems,
                "message": "The project changed since validation. Please regenerate the changes.",
            }

        # --- Transactional apply ---------------------------------------
        operation_id = uuid.uuid4().hex[:12]
        backup_dir = self._backup_dir(operation_id)
        backup_dir.mkdir(parents=True, exist_ok=True)
        completed: List[Dict[str, Any]] = []

        try:
            for p in patches:
                self._apply_one(root, backup_dir, p)
                completed.append(p)
            self._verify_applied(root, patches)
        except Exception as exc:
            logger.error(f"Apply failed, rolling back: {exc}", exc_info=True)
            self._reverse_changes(root, backup_dir, completed)
            return {
                "status": "ROLLED_BACK",
                "plan_id": plan_id,
                "operation_id": operation_id,
                "error": str(exc),
                "message": "Update failed and was rolled back. No partial changes remain.",
            }

        # --- Record history --------------------------------------------
        operation = {
            "operation_id": operation_id,
            "plan_id": plan_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": bundle.get("request", ""),
            "intent": bundle.get("intent", ""),
            "status": "applied",
            "undone": False,
            "undone_at": None,
            "backup_dir": str(backup_dir),
            "changes": [
                {
                    "path": p["path"],
                    "change_type": p["change_type"],
                    "new_path": p.get("new_path"),
                    "additions": p.get("additions", 0),
                    "removals": p.get("removals", 0),
                    "diff": p.get("diff", ""),
                }
                for p in patches
            ],
            "validation": {
                "status": report.get("validation_status"),
                "risk": report.get("risk", {}).get("level"),
                "tests": report.get("stages", {}).get("tests", {}).get("status"),
            },
        }
        self._append_history(operation)

        result = {
            "status": "SUCCESS",
            "plan_id": plan_id,
            "operation_id": operation_id,
            "applied": [{"path": p["path"], "change_type": p["change_type"],
                         "new_path": p.get("new_path")} for p in patches],
            "affected_paths": self._affected_paths(patches),
            "message": "Changes applied successfully.",
        }

        # Mark validation hand-off as applied.
        report.setdefault("next_phase", {})["applied"] = True

        # --- Optional Git commit ---------------------------------------
        if do_commit:
            result["git"] = self._git_commit(root, bundle.get("request", "Apply agent changes"),
                                             self._affected_paths(patches))
        return result

    # ------------------------------------------------------------------
    # Undo / rollback
    # ------------------------------------------------------------------

    def undo_last(self, project_root: str) -> Dict[str, Any]:
        self.project_path = str(Path(project_root).resolve())
        history = self._load_history()
        for op in reversed(history):
            if op["status"] == "applied" and not op["undone"]:
                return self._undo_operation(op)
        return {"status": "NOTHING_TO_UNDO", "message": "No applied changes to undo."}

    def rollback(self, operation_id: str, project_root: str) -> Dict[str, Any]:
        self.project_path = str(Path(project_root).resolve())
        history = self._load_history()
        for op in history:
            if op["operation_id"] == operation_id:
                if op["undone"]:
                    return {"status": "ALREADY_UNDONE", "operation_id": operation_id,
                            "message": "This operation was already rolled back."}
                return self._undo_operation(op)
        raise KeyError(f"No operation with id: {operation_id}")

    def _undo_operation(self, op: Dict[str, Any]) -> Dict[str, Any]:
        root = Path(self.project_path)
        backup_dir = Path(op["backup_dir"])
        try:
            self._reverse_changes(root, backup_dir, op["changes"])
        except Exception as exc:
            logger.error(f"Undo failed: {exc}", exc_info=True)
            return {"status": "FAILED", "operation_id": op["operation_id"], "error": str(exc)}

        op["undone"] = True
        op["undone_at"] = datetime.now(timezone.utc).isoformat()
        op["status"] = "undone"
        self._save_history(self._load_history_with(op))
        return {
            "status": "UNDONE",
            "operation_id": op["operation_id"],
            "affected_paths": self._affected_paths(op["changes"]),
            "message": "Previous version restored.",
        }

    # ------------------------------------------------------------------
    # History / backups
    # ------------------------------------------------------------------

    def get_history(self, project_root: str) -> List[Dict[str, Any]]:
        self.project_path = str(Path(project_root).resolve())
        # Newest first, omit large diffs from the list view.
        out = []
        for op in reversed(self._load_history()):
            out.append({
                "operation_id": op["operation_id"],
                "timestamp": op["timestamp"],
                "request": op["request"],
                "intent": op["intent"],
                "status": op["status"],
                "undone": op["undone"],
                "undone_at": op.get("undone_at"),
                "validation": op.get("validation", {}),
                "summary": self._change_summary(op["changes"]),
                "changes": [{k: c[k] for k in ("path", "change_type", "new_path", "additions", "removals")}
                            for c in op["changes"]],
            })
        return out

    def get_backups(self, project_root: str) -> List[Dict[str, Any]]:
        self.project_path = str(Path(project_root).resolve())
        out = []
        for op in reversed(self._load_history()):
            bdir = Path(op["backup_dir"])
            out.append({
                "operation_id": op["operation_id"],
                "timestamp": op["timestamp"],
                "request": op["request"],
                "exists": bdir.exists(),
                "restorable": bdir.exists() and not op["undone"],
                "file_count": len(op["changes"]),
            })
        return out

    # ------------------------------------------------------------------
    # Patch application primitives
    # ------------------------------------------------------------------

    def _apply_one(self, root: Path, backup_dir: Path, p: Dict[str, Any]) -> None:
        ctype = p["change_type"]
        rel = p["path"]
        full = (root / rel).resolve()
        self._ensure_inside(root, full)

        if ctype == "modify":
            self._backup(full, backup_dir, rel)
            self._atomic_write(full, p.get("after", ""))
        elif ctype == "create":
            self._atomic_write(full, p.get("after", ""))
        elif ctype == "delete":
            self._backup(full, backup_dir, rel)
            if full.exists():
                full.unlink()
        elif ctype == "rename":
            new_rel = p.get("new_path")
            if not new_rel:
                raise ValueError(f"rename change for {rel} has no new_path")
            new_full = (root / new_rel).resolve()
            self._ensure_inside(root, new_full)
            self._backup(full, backup_dir, rel)
            new_full.parent.mkdir(parents=True, exist_ok=True)
            os.replace(full, new_full)
        else:
            raise ValueError(f"Unknown change_type: {ctype}")

    def _reverse_changes(self, root: Path, backup_dir: Path, changes: List[Dict[str, Any]]) -> None:
        # Reverse in opposite order for safety.
        for p in reversed(changes):
            ctype = p["change_type"]
            rel = p["path"]
            full = (root / rel).resolve()
            if ctype in ("modify", "delete"):
                self._restore(backup_dir, rel, full)
            elif ctype == "create":
                if full.exists():
                    full.unlink()
            elif ctype == "rename":
                new_full = (root / p["new_path"]).resolve()
                if new_full.exists():
                    full.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(new_full, full)

    def _verify_disk_state(self, root: Path, patches: List[Dict[str, Any]]) -> List[str]:
        problems = []
        for p in patches:
            ctype = p["change_type"]
            full = (root / p["path"]).resolve()
            if ctype == "modify":
                if not full.exists():
                    problems.append(f"{p['path']} no longer exists.")
                elif self._read(full) != p.get("before", ""):
                    problems.append(f"{p['path']} changed since validation.")
            elif ctype == "create":
                if full.exists():
                    problems.append(f"{p['path']} already exists.")
            elif ctype == "delete":
                if not full.exists():
                    problems.append(f"{p['path']} no longer exists.")
            elif ctype == "rename":
                if not full.exists():
                    problems.append(f"{p['path']} no longer exists.")
        return problems

    def _verify_applied(self, root: Path, patches: List[Dict[str, Any]]) -> None:
        for p in patches:
            ctype = p["change_type"]
            full = (root / p["path"]).resolve()
            if ctype in ("modify", "create"):
                if not full.exists():
                    raise IOError(f"{p['path']} was not written.")
                if self._read(full) != p.get("after", ""):
                    raise IOError(f"{p['path']} content verification failed.")
            elif ctype == "delete":
                if full.exists():
                    raise IOError(f"{p['path']} was not deleted.")

    # ------------------------------------------------------------------
    # Git integration (optional, never required)
    # ------------------------------------------------------------------

    def git_status(self, project_root: str) -> Dict[str, Any]:
        root = str(Path(project_root).resolve())
        inside = self._git(root, "rev-parse", "--is-inside-work-tree")
        if not inside or inside.returncode != 0 or "true" not in (inside.stdout or "").lower():
            return {"is_repo": False}
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")
        porcelain = self._git(root, "status", "--porcelain")
        modified, staged, untracked = [], [], []
        for line in (porcelain.stdout or "").splitlines() if porcelain else []:
            if not line:
                continue
            x, y, path = line[0], line[1], line[3:]
            if x == "?" and y == "?":
                untracked.append(path)
            else:
                if x not in (" ", "?"):
                    staged.append(path)
                if y not in (" ", "?"):
                    modified.append(path)
        return {
            "is_repo": True,
            "branch": (branch.stdout or "").strip() if branch else None,
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
        }

    def _git_commit(self, root: Path, message: str, files: List[str]) -> Dict[str, Any]:
        status = self.git_status(str(root))
        if not status.get("is_repo"):
            return {"committed": False, "reason": "not a git repository"}
        try:
            for f in files:
                self._git(str(root), "add", "--", f)
            res = self._git(str(root), "commit", "-m", f"[Brownfield Agent] {message}")
            ok = res is not None and res.returncode == 0
            return {"committed": ok, "branch": status.get("branch"),
                    "output": ((res.stdout or "") + (res.stderr or "")).strip()[-400:] if res else ""}
        except Exception as exc:
            return {"committed": False, "reason": str(exc)}

    @staticmethod
    def _git(cwd: str, *args) -> Optional[subprocess.CompletedProcess]:
        try:
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                  text=True, timeout=20)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers — fs
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_inside(root: Path, full: Path) -> None:
        try:
            full.relative_to(root.resolve())
        except ValueError:
            raise ValueError(f"Path escapes project root: {full}")

    @staticmethod
    def _atomic_write(full: Path, content: str) -> None:
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_name(full.name + ".brownfield-tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, full)

    @staticmethod
    def _read(full: Path) -> str:
        try:
            return full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _backup(full: Path, backup_dir: Path, rel: str) -> None:
        if full.exists():
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full, dest)

    @staticmethod
    def _restore(backup_dir: Path, rel: str, full: Path) -> None:
        src = backup_dir / rel
        if src.exists():
            full.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, full)

    @staticmethod
    def _affected_paths(changes: List[Dict[str, Any]]) -> List[str]:
        paths = []
        for c in changes:
            paths.append(c["path"])
            if c.get("new_path"):
                paths.append(c["new_path"])
        return sorted(set(paths))

    @staticmethod
    def _change_summary(changes: List[Dict[str, Any]]) -> Dict[str, int]:
        return {
            "modified": sum(1 for c in changes if c["change_type"] == "modify"),
            "created": sum(1 for c in changes if c["change_type"] == "create"),
            "deleted": sum(1 for c in changes if c["change_type"] == "delete"),
            "renamed": sum(1 for c in changes if c["change_type"] == "rename"),
        }

    @staticmethod
    def _blocked(message: str) -> Dict[str, Any]:
        return {"status": "BLOCKED", "message": message}

    # ------------------------------------------------------------------
    # Helpers — persistence
    # ------------------------------------------------------------------

    def _project_key(self) -> str:
        return hashlib.md5(self.project_path.encode("utf-8")).hexdigest()

    def _history_file(self) -> Path:
        return _HISTORY_DIR / f"{self._project_key()}.json"

    def _backup_dir(self, operation_id: str) -> Path:
        return _BACKUP_ROOT / self._project_key() / operation_id

    def _load_history(self) -> List[Dict[str, Any]]:
        f = self._history_file()
        try:
            if f.exists():
                return json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not read change history: {exc}")
        return []

    def _load_history_with(self, updated: Dict[str, Any]) -> List[Dict[str, Any]]:
        history = self._load_history()
        for i, op in enumerate(history):
            if op["operation_id"] == updated["operation_id"]:
                history[i] = updated
                break
        return history

    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        f = self._history_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(history[-MAX_HISTORY:], indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Could not save change history: {exc}")

    def _append_history(self, operation: Dict[str, Any]) -> None:
        history = self._load_history()
        history.append(operation)
        self._save_history(history)


# Singleton instance
source_update_service = SourceUpdateEngine()
