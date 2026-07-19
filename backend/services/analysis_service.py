import os
import time
import json
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from backend.services.parsers.manager import ParserManager

logger = logging.getLogger(__name__)

# Folders to hide from statistics and analysis
HIDDEN_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vs", ".vscode", "dist", "build", ".gradle",
    ".mypy_cache", ".pytest_cache", ".tox",
}

class AnalysisManager:
    """
    Project Analysis Engine. Scans workspace files in the background,
    extracts structural metadata incrementally, builds a knowledge model,
    and caches results on disk.
    """

    def __init__(self):
        self.status = "idle"  # idle, analyzing, completed, failed
        self.progress = 0.0
        self.total_files = 0
        self.processed_files = 0
        self.current_file = ""
        self.error_message = ""
        
        # Active project state
        self.project_path = ""
        self.analyzed_at = ""
        self.files: Dict[str, Dict[str, Any]] = {}
        self.modules: Dict[str, List[str]] = {}
        self.relationships: Dict[str, Any] = {
            "imports": {},          # file -> list of imported files (internal)
            "external_imports": {},  # file -> list of external packages/modules
            "inherits": {},         # class_name -> list of base class names
            "calls": {}             # function/method -> list of functions it references
        }
        self.stats: Dict[str, Any] = {
            "files": 0,
            "folders": 0,
            "classes": 0,
            "functions": 0,
            "modules": 0,
            "languages": {}
        }
        
        self._lock = asyncio.Lock()
        self._active_task: Optional[asyncio.Task] = None

    def get_status_summary(self) -> Dict[str, Any]:
        """Return the current analysis state and stats for API consumption."""
        return {
            "status": self.status,
            "progress": round(self.progress, 1),
            "current_file": self.current_file,
            "error": self.error_message,
            "project_path": self.project_path,
            "analyzed_at": self.analyzed_at,
            "stats": self.stats
        }

    def trigger_analysis(self, project_root: str, background_tasks = None):
        """Trigger project analysis. Cancels active run if any, and restarts."""
        # Run in a background task
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        
        # Start new async background task
        self._active_task = asyncio.create_task(self.run_analysis(project_root))

    async def run_analysis(self, project_root: str, force: bool = False):
        async with self._lock:
            resolved_path = str(Path(project_root).resolve())
            if not force and self.status == "completed" and self.project_path == resolved_path and self.files:
                logger.info(f"Reusing active project analysis for {self.project_path}")
                return

            try:
                self.status = "analyzing"
                self.progress = 0.0
                self.error_message = ""
                self.project_path = resolved_path
                
                # Step 1: Scan filesystem
                logger.info(f"Scanning files in project: {self.project_path}")
                all_paths: List[Path] = []
                folders_count = 0
                
                for root, dirs, files in os.walk(self.project_path):
                    # In-place modify dirs to skip hidden folders
                    dirs[:] = [d for d in dirs if d not in HIDDEN_DIRS]
                    folders_count += len(dirs)
                    
                    for f in files:
                        file_path = Path(root) / f
                        all_paths.append(file_path)
                
                # Step 2: Load Cache
                cache_path = self._get_cache_path(self.project_path)
                cache_data = self._load_cache(cache_path)
                
                cached_files = {}
                if cache_data and cache_data.get("project_path") == self.project_path:
                    cached_files = cache_data.get("files", {})
                
                # Step 3: Filter supported files for parsing
                supported_paths = [p for p in all_paths if ParserManager.supports(str(p))]
                self.total_files = len(supported_paths)
                self.processed_files = 0
                
                new_files_data = {}
                
                # Step 4: Parse files incrementally
                for p in supported_paths:
                    rel_path = str(p.relative_to(self.project_path)).replace("\\", "/")
                    self.current_file = rel_path
                    
                    try:
                        stat = p.stat()
                        mtime = stat.st_mtime
                        size = stat.st_size
                        
                        # Check cache
                        cached = cached_files.get(rel_path)
                        if cached and cached.get("mtime") == mtime and cached.get("size") == size:
                            # Re-use cache
                            new_files_data[rel_path] = cached
                        else:
                            # Read & parse file
                            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                                content = fh.read()
                            
                            parser = ParserManager.get_parser(str(p))
                            parsed = parser.parse(content, rel_path) if parser else {"classes": [], "functions": [], "imports": []}
                            
                            new_files_data[rel_path] = {
                                "path": rel_path,
                                "language": p.suffix.lstrip(".").lower(),
                                "mtime": mtime,
                                "size": size,
                                "classes": parsed.get("classes", []),
                                "functions": parsed.get("functions", []),
                                "imports": parsed.get("imports", []),
                                "summary": self._extract_file_summary(content, parsed)
                            }
                    except Exception as exc:
                        logger.error(f"Error parsing file {rel_path}: {exc}")
                        # Keep basic metadata
                        new_files_data[rel_path] = {
                            "path": rel_path,
                            "language": p.suffix.lstrip(".").lower(),
                            "mtime": 0.0,
                            "size": 0,
                            "classes": [],
                            "functions": [],
                            "imports": [],
                            "summary": f"Parsing failed: {exc}"
                        }
                    
                    self.processed_files += 1
                    if self.total_files > 0:
                        self.progress = (self.processed_files / self.total_files) * 100

                    # Periodically yield to the event loop to keep the IDE UI
                    # responsive (and allow cancellation) without adding a real
                    # per-file delay. sleep(0) yields without sleeping.
                    if self.processed_files % 20 == 0:
                        await asyncio.sleep(0)

                self.files = new_files_data
                
                # Step 5: Build Module structures
                # Modules are logical directories directly under root, or directories that contain source code
                self.modules = {}
                for rel_path in self.files.keys():
                    parts = rel_path.split("/")
                    if len(parts) > 1:
                        module_name = parts[0]
                    else:
                        module_name = "root"
                    
                    if module_name not in self.modules:
                        self.modules[module_name] = []
                    self.modules[module_name].append(rel_path)
                
                # Step 6: Build relationships
                self.relationships = {
                    "imports": {},
                    "external_imports": {},
                    "inherits": {},
                    "calls": {}
                }
                
                all_rel_paths = list(self.files.keys())
                for rel_path, file_data in self.files.items():
                    self.relationships["imports"][rel_path] = []
                    self.relationships["external_imports"][rel_path] = []
                    
                    # Map imports to internal files
                    for imp in file_data.get("imports", []):
                        source = imp.get("source", "")
                        resolved = self._resolve_import(source, rel_path, all_rel_paths)
                        if resolved:
                            if resolved not in self.relationships["imports"][rel_path]:
                                self.relationships["imports"][rel_path].append(resolved)
                        else:
                            if source not in self.relationships["external_imports"][rel_path]:
                                self.relationships["external_imports"][rel_path].append(source)
                    
                    # Map inheritance
                    for cls in file_data.get("classes", []):
                        class_name = cls.get("name", "")
                        bases = cls.get("bases", [])
                        if bases:
                            self.relationships["inherits"][class_name] = bases

                # Step 7: Calculate statistics
                classes_count = sum(len(f.get("classes", [])) for f in self.files.values())
                functions_count = sum(len(f.get("functions", [])) for f in self.files.values()) + \
                                  sum(sum(len(c.get("methods", [])) for c in f.get("classes", [])) for f in self.files.values())
                
                # Calculate language breakdown based on parsed file extensions
                lang_breakdown = {}
                for p in all_paths:
                    ext = p.suffix.lstrip(".").upper()
                    if not ext:
                        ext = "NO EXT"
                    lang_breakdown[ext] = lang_breakdown.get(ext, 0) + 1
                
                total_all_files = len(all_paths)
                lang_percentages = {}
                if total_all_files > 0:
                    for lang, count in lang_breakdown.items():
                        percentage = round((count / total_all_files) * 100, 1)
                        # Only show languages above 1% or limit to top 5
                        if percentage >= 1.0:
                            lang_percentages[lang] = percentage
                
                # Sort languages by percentage
                lang_percentages = dict(sorted(lang_percentages.items(), key=lambda item: item[1], reverse=True))

                self.stats = {
                    "files": len(all_paths),
                    "folders": folders_count + 1,  # include root folder
                    "classes": classes_count,
                    "functions": functions_count,
                    "modules": len(self.modules),
                    "languages": lang_percentages
                }
                
                self.analyzed_at = datetime.now(timezone.utc).isoformat()
                
                # Save cache
                logger.info("Saving analysis cache to disk...")
                cache_payload = {
                    "project_path": self.project_path,
                    "analyzed_at": self.analyzed_at,
                    "stats": self.stats,
                    "modules": self.modules,
                    "relationships": self.relationships,
                    "files": self.files
                }
                self._save_cache(cache_path, cache_payload)
                
                self.status = "completed"
                self.progress = 100.0
                self.current_file = ""
                logger.info("Project analysis completed successfully.")
                
            except asyncio.CancelledError:
                logger.info("Analysis task was cancelled.")
                self.status = "idle"
            except Exception as exc:
                logger.error(f"Analysis failed: {exc}", exc_info=True)
                self.status = "failed"
                self.error_message = str(exc)

    def _get_cache_path(self, project_root: str) -> Path:
        resolved = str(Path(project_root).resolve())
        path_hash = hashlib.md5(resolved.encode('utf-8')).hexdigest()
        import platform
        if platform.system() == "Windows":
            base_dir = Path.home() / ".brownfield-ide"
        else:
            base_dir = Path("/tmp/.brownfield-ide")
        return base_dir / "analysis" / f"{path_hash}.json"

    def _load_cache(self, cache_path: Path) -> Optional[Dict[str, Any]]:
        try:
            if cache_path.exists():
                return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not load analysis cache: {exc}")
        return None

    def _save_cache(self, cache_path: Path, data: Dict[str, Any]):
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Could not save analysis cache: {exc}")

    def _extract_file_summary(self, content: str, parsed: Dict[str, Any]) -> str:
        """Extract a short single-line description of the file's purpose based on comments/docstrings."""
        # If there's a class docstring, use it
        for cls in parsed.get("classes", []):
            if cls.get("docstring"):
                return cls["docstring"].split("\n")[0].strip()
        # If there's a function docstring, use it
        for func in parsed.get("functions", []):
            if func.get("docstring"):
                return func["docstring"].split("\n")[0].strip()
        
        # Check first few lines for comments
        lines = content.splitlines()[:5]
        for line in lines:
            line = line.strip()
            if line.startswith("//"):
                return line[2:].strip()
            if line.startswith("#") and not line.startswith("#!"):
                return line[1:].strip()
                
        return "Source code file."

    def _resolve_import(self, source: str, importing_file: str, all_files: List[str]) -> Optional[str]:
        """Heuristically resolves import strings (Python, JS/TS, Java) into project relative paths."""
        if not source:
            return None
            
        importing_path = Path(importing_file)
        
        # Case 1: JavaScript/TypeScript relative imports (e.g. "./utils", "../components/Button")
        if source.startswith("."):
            importing_dir = importing_path.parent
            # Try to resolve relative path
            try:
                # Normalise path
                rel_resolved = (importing_dir / source).resolve()
                # Find matching file suffix in project
                for f in all_files:
                    f_path = Path(f)
                    # Check if relative target matches base path
                    # e.g., if rel_resolved matches relative project files
                    if f.endswith(source.lstrip(".")):
                        return f
                
                # Fallback check
                clean_src = source.lstrip("./").lstrip("../")
                for f in all_files:
                    if f.endswith(clean_src + ".js") or f.endswith(clean_src + ".ts") or f.endswith(clean_src + ".tsx"):
                        return f
            except Exception:
                pass

        # Case 2: Python package/module imports (e.g. "backend.services.workspace_service")
        # Replace dots with slashes and look for matches
        py_source = source.replace(".", "/")
        for f in all_files:
            if f.endswith(py_source + ".py") or f.endswith(py_source + "/__init__.py"):
                return f

        # Case 3: Java package imports (e.g. "com.brownfield.services.WorkspaceService")
        java_source = source.replace(".", "/")
        for f in all_files:
            if f.endswith(java_source + ".java"):
                return f

        # Check if source directly matches any suffix of files
        for f in all_files:
            if source in f:
                return f
                
        return None

# Singleton instance
analysis_manager = AnalysisManager()
