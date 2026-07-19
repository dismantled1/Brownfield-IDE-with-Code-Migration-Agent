"""
Workspace Service — manages the currently-open project and recent-projects list.

State is persisted to ~/.brownfield-ide/workspace.json so it survives
server restarts.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from backend.models.schemas import WorkspaceState, RecentProject

logger = logging.getLogger(__name__)

# Where we persist the workspace state
_STATE_DIR = Path.home() / ".brownfield-ide"
_STATE_FILE = _STATE_DIR / "workspace.json"

# Maximum number of recent projects to remember
MAX_RECENT = 20


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_state() -> WorkspaceState:
    """Load workspace state from disk, or return a default empty state."""
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            return WorkspaceState(**data)
    except Exception as exc:
        logger.warning(f"Could not load workspace state: {exc}")
    return WorkspaceState()


def _save_state(state: WorkspaceState) -> None:
    """Persist workspace state to disk."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error(f"Could not save workspace state: {exc}")


# In-memory cache — loaded once on first access
_state: Optional[WorkspaceState] = None


def _get_state() -> WorkspaceState:
    global _state
    if _state is None:
        _state = _load_state()
    return _state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_state() -> WorkspaceState:
    """Return the current workspace state."""
    return _get_state()


def open_project(path: str) -> WorkspaceState:
    """
    Set *path* as the current project and push it to the recent-projects list.
    Returns the updated state.
    """
    resolved = str(Path(path).resolve())
    project_name = Path(resolved).name

    state = _get_state()
    state.current_project = resolved

    # Update recents (move to front if already present)
    state.recent_projects = [r for r in state.recent_projects if r.path != resolved]
    state.recent_projects.insert(
        0,
        RecentProject(
            path=resolved,
            name=project_name,
            opened_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    state.recent_projects = state.recent_projects[:MAX_RECENT]

    _save_state(state)
    return state


def close_project() -> WorkspaceState:
    """Clear the current project without removing it from recents."""
    state = _get_state()
    state.current_project = None
    _save_state(state)
    return state


def get_recent_projects() -> List[RecentProject]:
    """Return the list of recently opened projects (most recent first)."""
    return _get_state().recent_projects


def get_current_project() -> Optional[str]:
    """Return the absolute path of the currently open project, or None."""
    return _get_state().current_project


def remove_recent(path: str) -> None:
    """Remove an entry from the recent-projects list."""
    state = _get_state()
    state.recent_projects = [r for r in state.recent_projects if r.path != path]
    _save_state(state)
