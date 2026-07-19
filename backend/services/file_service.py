"""
File Service — handles all file system operations for the Brownfield IDE.

Security model:
  - All paths passed in are RELATIVE to the project root.
  - _validate_path() resolves them to absolute and checks they stay
    inside the root (prevents path-traversal attacks).
  - The only endpoint that takes an absolute path is "open project".
"""

import os
import shutil
import zipfile
import aiofiles
from pathlib import Path
from typing import List, Optional

from backend.models.schemas import FileNode

# File extensions treated as binary (won't be opened in the editor)
BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o",
    ".class", ".jar", ".war", ".ear",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".tiff",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".mdb",
    ".pyc", ".pyd", ".pyo",
    ".woff", ".woff2", ".eot", ".ttf", ".otf",
}

# Folders to hide from the explorer by default
HIDDEN_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vs", ".vscode", "dist", "build", ".gradle",
    ".mypy_cache", ".pytest_cache", ".tox",
}

# Max file size the editor will load (10 MB)
MAX_EDITOR_FILE_SIZE = 10 * 1024 * 1024

# Brownfield IDE projects extraction root
PROJECTS_DIR = Path.home() / "brownfield-projects"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_path(project_root: str, relative_path: str) -> Path:
    """
    Resolve *relative_path* against *project_root* and verify it stays
    inside the root directory. Raises ValueError on traversal attempt.
    """
    root = Path(project_root).resolve()
    if not relative_path or relative_path in ("", "/", "."):
        return root
    # Normalise separators
    clean = relative_path.replace("\\", "/").lstrip("/")
    full = (root / clean).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal detected: '{relative_path}'")
    return full


def _build_node(path: Path, root: Path, max_depth: int, current_depth: int = 0) -> FileNode:
    """Recursively build a FileNode tree up to *max_depth*."""
    try:
        stat = path.stat()
    except (PermissionError, OSError):
        stat = None

    relative = ""
    try:
        rel = path.relative_to(root)
        relative = str(rel).replace("\\", "/")
    except ValueError:
        pass

    if path.is_file():
        return FileNode(
            name=path.name,
            path=relative,
            type="file",
            extension=path.suffix.lstrip(".").lower() or None,
            size=stat.st_size if stat else None,
            modified=stat.st_mtime if stat else None,
            children=None,
        )

    # Directory
    children: Optional[List[FileNode]] = None
    if current_depth < max_depth:
        children = []
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda e: (e.is_file(), e.name.lower()),
            )
            for entry in entries:
                # Skip heavily polluted dirs to keep the tree useful
                if entry.is_dir() and entry.name in HIDDEN_DIRS:
                    continue
                children.append(
                    _build_node(entry, root, max_depth, current_depth + 1)
                )
        except PermissionError:
            pass

    return FileNode(
        name=path.name if relative else root.name,
        path=relative,
        type="folder",
        extension=None,
        size=None,
        modified=stat.st_mtime if stat else None,
        children=children,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tree(project_root: str, depth: int = 1) -> FileNode:
    """Return the project tree at the given depth (lazy-loading friendly)."""
    root = Path(project_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")
    return _build_node(root, root, max_depth=depth)


def get_children(project_root: str, relative_path: str) -> List[FileNode]:
    """Return immediate children of a directory (one level, unloaded subdirs)."""
    full_path = _validate_path(project_root, relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"Path not found: {relative_path}")
    if not full_path.is_dir():
        raise ValueError(f"Not a directory: {relative_path}")

    root = Path(project_root).resolve()
    children: List[FileNode] = []
    try:
        entries = sorted(
            full_path.iterdir(),
            key=lambda e: (e.is_file(), e.name.lower()),
        )
        for entry in entries:
            if entry.is_dir() and entry.name in HIDDEN_DIRS:
                continue
            children.append(_build_node(entry, root, max_depth=0))
    except PermissionError as exc:
        raise PermissionError(f"Cannot read directory: {exc}") from exc
    return children


async def read_file(project_root: str, relative_path: str) -> dict:
    """Read a text file and return its content."""
    full_path = _validate_path(project_root, relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if not full_path.is_file():
        raise ValueError(f"Not a file: {relative_path}")

    ext = full_path.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        raise ValueError(f"Binary file — cannot open in editor: {full_path.name}")

    size = full_path.stat().st_size
    if size > MAX_EDITOR_FILE_SIZE:
        raise ValueError(
            f"File too large for the editor ({size // 1024 // 1024} MB). "
            f"Max is {MAX_EDITOR_FILE_SIZE // 1024 // 1024} MB."
        )

    async with aiofiles.open(str(full_path), mode="r", encoding="utf-8", errors="replace") as f:
        content = await f.read()

    return {
        "path": relative_path,
        "content": content,
        "size": size,
        "encoding": "utf-8",
        "language": _ext_to_language(ext),
    }


async def write_file(project_root: str, relative_path: str, content: str) -> None:
    """Write content to a file (creates parent directories as needed)."""
    full_path = _validate_path(project_root, relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(str(full_path), mode="w", encoding="utf-8") as f:
        await f.write(content)


def create_file(project_root: str, relative_path: str) -> FileNode:
    """Create a new empty file."""
    full_path = _validate_path(project_root, relative_path)
    if full_path.exists():
        raise FileExistsError(f"Already exists: {relative_path}")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.touch()
    return _build_node(full_path, Path(project_root).resolve(), max_depth=0)


def create_folder(project_root: str, relative_path: str) -> FileNode:
    """Create a new directory."""
    full_path = _validate_path(project_root, relative_path)
    if full_path.exists():
        raise FileExistsError(f"Already exists: {relative_path}")
    full_path.mkdir(parents=True, exist_ok=True)
    return _build_node(full_path, Path(project_root).resolve(), max_depth=0)


def delete_item(project_root: str, relative_path: str) -> None:
    """Delete a file or folder (recursive)."""
    full_path = _validate_path(project_root, relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"Not found: {relative_path}")
    if full_path.is_file() or full_path.is_symlink():
        full_path.unlink()
    else:
        shutil.rmtree(str(full_path))


def rename_item(project_root: str, relative_path: str, new_name: str) -> FileNode:
    """Rename a file or folder (same directory, new name)."""
    full_old = _validate_path(project_root, relative_path)
    if not full_old.exists():
        raise FileNotFoundError(f"Not found: {relative_path}")

    new_full = full_old.parent / new_name
    # Ensure new path still within root
    root = Path(project_root).resolve()
    try:
        new_full.resolve().relative_to(root)
    except ValueError:
        raise ValueError(f"Rename would escape project root")

    if new_full.exists():
        raise FileExistsError(f"'{new_name}' already exists in this directory")

    full_old.rename(new_full)
    return _build_node(new_full, root, max_depth=0)


def search_files(project_root: str, query: str, max_results: int = 100) -> List[FileNode]:
    """Search for files/folders whose names contain *query* (case-insensitive)."""
    root = Path(project_root).resolve()
    results: List[FileNode] = []
    q = query.lower()

    for path in root.rglob("*"):
        if len(results) >= max_results:
            break
        # Skip hidden dirs
        parts = path.relative_to(root).parts
        if any(p in HIDDEN_DIRS for p in parts):
            continue
        if q in path.name.lower():
            results.append(_build_node(path, root, max_depth=0))

    return results


async def extract_zip(zip_bytes_path: str, destination_dir: Optional[str] = None) -> str:
    """
    Extract a ZIP archive (already saved to *zip_bytes_path*) into
    *destination_dir*.  Returns the absolute path of the extracted project.

    ZIP entries are validated for path-traversal (zip-slip protection).
    """
    zip_path = Path(zip_bytes_path)
    archive_name = zip_path.stem  # e.g. "my-project" from "my-project.zip"

    if destination_dir:
        dest = Path(destination_dir).resolve()
    else:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        dest = PROJECTS_DIR / archive_name

    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), "r") as zf:
        # Zip-slip protection — verify each member resolves to a path *inside*
        # dest. Uses relative_to (not a string-prefix check, which would treat
        # "/a/proj-evil" as inside "/a/proj").
        for member in zf.namelist():
            member_path = (dest / member).resolve()
            try:
                member_path.relative_to(dest)
            except ValueError:
                raise ValueError(f"Zip-slip detected: {member}")
        # Stream extraction member by member
        for member in zf.infolist():
            zf.extract(member, str(dest))

    # If the archive had a single top-level directory, use that as project root
    entries = [e for e in dest.iterdir()]
    if len(entries) == 1 and entries[0].is_dir():
        return str(entries[0])
    return str(dest)


# ---------------------------------------------------------------------------
# Helper: extension → Monaco language ID
# ---------------------------------------------------------------------------

_LANG_MAP = {
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "py": "python",
    "java": "java",
    "kt": "kotlin",
    "kts": "kotlin",
    "cs": "csharp",
    "cpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "c": "c",
    "h": "c",
    "hpp": "cpp",
    "go": "go",
    "rs": "rust",
    "rb": "ruby",
    "php": "php",
    "swift": "swift",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "scss",
    "sass": "scss",
    "less": "less",
    "json": "json",
    "jsonc": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
    "svg": "xml",
    "md": "markdown",
    "markdown": "markdown",
    "sql": "sql",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "bat": "bat",
    "cmd": "bat",
    "ps1": "powershell",
    "psm1": "powershell",
    "dockerfile": "dockerfile",
    "tf": "hcl",
    "hcl": "hcl",
    "toml": "ini",
    "ini": "ini",
    "cfg": "ini",
    "env": "ini",
    "txt": "plaintext",
    "log": "plaintext",
    "gitignore": "plaintext",
    "editorconfig": "ini",
    "properties": "ini",
}


def _ext_to_language(ext: str) -> str:
    """Map a file extension (with leading dot) to a Monaco language ID."""
    clean = ext.lstrip(".").lower()
    return _LANG_MAP.get(clean, "plaintext")
