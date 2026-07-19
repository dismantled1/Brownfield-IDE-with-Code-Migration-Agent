"""
Migration Analysis Engine — Phase 2 Code Migration Agent
=========================================================
Performs deterministic static code analysis to understand source project structure,
languages, frameworks, architecture, component breakdown, dependencies, entry points,
key assets, and migration plan without generating code or calling LLMs.
"""

import os
import re
import json
import time
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from backend.models.schemas import (
    MigrationAnalysisRequest,
    MigrationComponentBreakdown,
    MigrationAssetCategory,
    MigrationPlan,
    MigrationStatusResponse
)

logger = logging.getLogger(__name__)

# Hidden folders to exclude from scanning
HIDDEN_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vs", ".vscode", "dist", "build", ".gradle",
    ".mypy_cache", ".pytest_cache", ".tox", "target", "bin", "obj"
}

# Mapping of file extension to language
EXTENSION_LANGUAGE_MAP = {
    ".java": "Java",
    ".py": "Python",
    ".cs": "C#",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".php": "PHP",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".c": "C++",
    ".h": "C++",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".scala": "Scala"
}

# Known framework indicator patterns
FRAMEWORK_PATTERNS = {
    "Spring Boot": [r"@SpringBootApplication", r"spring-boot-starter", r"org\.springframework\.boot"],
    ".NET / ASP.NET": [r"Microsoft\.AspNetCore", r"Microsoft\.NET\.Sdk", r"using System\.Web"],
    "FastAPI": [r"from fastapi import", r"FastAPI\("],
    "Flask": [r"from flask import", r"Flask\(__name__\)"],
    "Django": [r"django\.db", r"django\.urls", r"DJANGO_SETTINGS_MODULE"],
    "React": [r"from ['\"]react['\"]", r"import React", r"ReactDOM\.render", r"createRoot"],
    "Angular": [r"@angular/core", r"angular\.json"],
    "Vue": [r"from ['\"]vue['\"]", r"createApp\(", r"\.vue$"],
    "Express / Node": [r"require\(['\"]express['\"]\)", r"import express from", r"package\.json"],
    "Laravel": [r"Illuminate\\", r"artisan", r"laravel/framework"],
    "Gin (Go)": [r"github\.com/gin-gonic/gin"],
    "Actix (Rust)": [r"actix_web"],
}

class MigrationService:
    """
    Project Analysis Engine for AI Code Migration Agent (Phase 2).
    Tracks active scan state, performs step-by-step progress logging,
    caches analysis results, and builds the complete Migration Plan.
    """

    def __init__(self):
        self.status = "idle"  # idle, analyzing, completed, failed
        self.progress = 0.0
        self.current_step = ""
        self.current_file = ""
        self.error_message = ""
        self.step_logs: List[Dict[str, Any]] = []
        self.active_plan: Optional[MigrationPlan] = None

        self._lock = asyncio.Lock()
        self._active_task: Optional[asyncio.Task] = None
        self._cache: Dict[str, Tuple[float, MigrationPlan]] = {}

    def get_status_summary(self) -> MigrationStatusResponse:
        """Return status and active plan for API consumption."""
        return MigrationStatusResponse(
            status=self.status,
            progress=round(self.progress, 1),
            current_step=self.current_step,
            current_file=self.current_file,
            step_logs=self.step_logs,
            error=self.error_message,
            plan=self.active_plan
        )

    def trigger_analysis(self, project_root: str, req: MigrationAnalysisRequest):
        """Trigger background migration analysis."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()

        self._active_task = asyncio.create_task(self.run_analysis(project_root, req))

    async def run_analysis(self, project_root: str, req: MigrationAnalysisRequest):
        """Executes full migration analysis asynchronously with real step logs."""
        async with self._lock:
            try:
                project_path = str(Path(project_root).resolve())
                self.status = "analyzing"
                self.progress = 0.0
                self.error_message = ""
                self.step_logs = []
                self.active_plan = None

                # ------------------------------------------------------------
                # Step 1: Project Loaded
                # ------------------------------------------------------------
                self._log_step(10.0, "Project Loaded", f"Scanning workspace: {project_path}")
                await asyncio.sleep(0.1)

                all_files, total_bytes = self._scan_project_files(project_path)
                mtime_hash = self._compute_mtime_hash(project_path, all_files)
                cache_key = f"{project_path}:{req.scope}:{req.target_path or ''}:{req.source_lang}:{req.target_lang}"

                if cache_key in self._cache:
                    cached_time, cached_plan = self._cache[cache_key]
                    if cached_time == mtime_hash:
                        logger.info("Reusing cached Migration Plan")
                        self._log_step(100.0, "Analysis Completed", "Loaded cached migration analysis results.")
                        self.status = "completed"
                        self.active_plan = cached_plan
                        return

                # ------------------------------------------------------------
                # Step 2: Detecting Source Language
                # ------------------------------------------------------------
                self._log_step(25.0, "Detecting Source Language", "Analyzing file extensions and build system metadata...")
                await asyncio.sleep(0.1)

                lang_stats, primary_lang, secondary_langs = self._detect_languages(project_path, all_files, req.source_lang)

                # ------------------------------------------------------------
                # Step 3: Detecting Framework
                # ------------------------------------------------------------
                self._log_step(40.0, "Detecting Framework", "Inspecting dependencies, package configs, and import statements...")
                await asyncio.sleep(0.1)

                ext_deps, db_conns = self._detect_external_dependencies_and_db(project_path, all_files)
                detected_framework = self._detect_framework(project_path, all_files, ext_deps)
                project_type = self._detect_project_type(all_files, detected_framework, ext_deps)

                # ------------------------------------------------------------
                # Step 4: Analyzing Project Structure
                # ------------------------------------------------------------
                self._log_step(55.0, "Analyzing Project Structure", "Building module graph and entry points mapping...")
                await asyncio.sleep(0.1)

                entry_points = self._detect_entry_points(all_files)
                internal_deps = self._analyze_internal_dependencies(project_path, all_files)

                # ------------------------------------------------------------
                # Step 5: Detecting Three-Tier Architecture
                # ------------------------------------------------------------
                self._log_step(70.0, "Detecting Three-Tier Architecture", "Classifying Presentation, Business, and Data layers...")
                await asyncio.sleep(0.1)

                layers, arch_pattern = self._detect_architecture_and_layers(all_files)

                # ------------------------------------------------------------
                # Step 6: Identifying Modules & Component Breakdown
                # ------------------------------------------------------------
                self._log_step(80.0, "Identifying Modules", "Categorizing Controllers, Services, Repositories, Models, DTOs, etc...")
                await asyncio.sleep(0.1)

                components = self._classify_components(all_files)
                assets = self._categorize_assets(all_files)

                # ------------------------------------------------------------
                # Step 7: Analyzing Dependencies & Scope Filtering
                # ------------------------------------------------------------
                self._log_step(90.0, "Analyzing Dependencies", f"Filtering scope '{req.scope}' (target: {req.target_path or 'all'})...")
                await asyncio.sleep(0.1)

                included_files, excluded_files = self._filter_scope(
                    all_files, req.scope, req.target_path, layers, components
                )

                # ------------------------------------------------------------
                # Step 8: Building Migration Plan
                # ------------------------------------------------------------
                self._log_step(95.0, "Building Migration Plan", "Synthesizing complexity score and markdown report...")
                await asyncio.sleep(0.1)

                complexity = self._estimate_complexity(
                    included_files_count=len(included_files),
                    total_loc=total_bytes // 35,
                    layers_count=len([l for l in layers.values() if l]),
                    ext_deps_count=len(ext_deps),
                    db_conns_count=len(db_conns)
                )

                target_l = req.target_language or req.target_lang or "Java"
                src_v = req.source_version
                tgt_v = req.target_version

                plan = MigrationPlan(
                    project_path=project_path,
                    source_language=primary_lang,
                    secondary_languages=secondary_langs,
                    target_language=target_l,
                    source_version=src_v,
                    target_version=tgt_v,
                    project_type=project_type,
                    framework=detected_framework,
                    architecture=arch_pattern,
                    scope=req.scope,
                    target_path=req.target_path,
                    files_included=included_files,
                    files_excluded=excluded_files,
                    total_files_count=len(all_files),
                    included_files_count=len(included_files),
                    excluded_files_count=len(excluded_files),
                    components=components,
                    assets=assets,
                    internal_dependencies=internal_deps,
                    external_dependencies=ext_deps,
                    database_connections=db_conns,
                    entry_points=entry_points,
                    estimated_complexity=complexity,
                    estimated_size_loc=total_bytes // 35,
                    estimated_size_bytes=total_bytes
                )

                # Generate markdown report
                plan.report_markdown = self._generate_markdown_report(plan, req)

                # Cache plan
                self._cache[cache_key] = (mtime_hash, plan)
                self.active_plan = plan

                # ------------------------------------------------------------
                # Step 9: Analysis Completed
                # ------------------------------------------------------------
                self._log_step(100.0, "Analysis Completed", "Migration analysis engine completed successfully.")
                self.status = "completed"

            except asyncio.CancelledError:
                logger.info("Migration analysis cancelled.")
                self.status = "idle"
            except Exception as exc:
                logger.error(f"Migration analysis failed: {exc}", exc_info=True)
                self.status = "failed"
                self.error_message = str(exc)
                self._log_step(self.progress, "Analysis Failed", f"Error: {exc}")

    # ---------------------------------------------------------------------------
    # Helper Scanner & Classifier Methods
    # ---------------------------------------------------------------------------

    def _log_step(self, progress: float, step_name: str, detail: str):
        """Update active step and append log entry."""
        self.progress = progress
        self.current_step = step_name
        self.step_logs.append({
            "step": step_name,
            "detail": detail,
            "progress": round(progress, 1),
            "timestamp": time.strftime("%H:%M:%S")
        })

    def _scan_project_files(self, project_root: str) -> Tuple[List[Dict[str, Any]], int]:
        """Scan filesystem for all project files, returning metadata and total size."""
        all_files = []
        total_size = 0
        root_path = Path(project_root)

        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in HIDDEN_DIRS]
            for f in files:
                full_path = Path(root) / f
                try:
                    rel_path = str(full_path.relative_to(root_path)).replace("\\", "/")
                    stat = full_path.stat()
                    total_size += stat.st_size
                    all_files.append({
                        "rel_path": rel_path,
                        "name": f,
                        "suffix": full_path.suffix.lower(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime
                    })
                except Exception:
                    continue

        return all_files, total_size

    def _compute_mtime_hash(self, project_root: str, all_files: List[Dict[str, Any]]) -> float:
        """Compute aggregate modification timestamp hash for caching."""
        if not all_files:
            return 0.0
        return sum(f["mtime"] for f in all_files[:50])

    def _detect_languages(
        self, project_root: str, all_files: List[Dict[str, Any]], user_selected: Optional[str]
    ) -> Tuple[Dict[str, int], str, Dict[str, float]]:
        """Detect primary and secondary source languages."""
        lang_counts: Dict[str, int] = {}
        total_source = 0

        for f in all_files:
            lang = EXTENSION_LANGUAGE_MAP.get(f["suffix"])
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
                total_source += 1

        # Check build files for strong language signals
        root_files = {f["name"].lower() for f in all_files if "/" not in f["rel_path"]}
        if "pom.xml" in root_files or "build.gradle" in root_files:
            lang_counts["Java"] = lang_counts.get("Java", 0) + 10
        if "requirements.txt" in root_files or "pyproject.toml" in root_files or "setup.py" in root_files:
            lang_counts["Python"] = lang_counts.get("Python", 0) + 10
        if any(f.endswith(".csproj") or f.endswith(".sln") for f in root_files):
            lang_counts["C#"] = lang_counts.get("C#", 0) + 10
        if "cargo.toml" in root_files:
            lang_counts["Rust"] = lang_counts.get("Rust", 0) + 10
        if "go.mod" in root_files:
            lang_counts["Go"] = lang_counts.get("Go", 0) + 10
        if "composer.json" in root_files:
            lang_counts["PHP"] = lang_counts.get("PHP", 0) + 10

        if not lang_counts:
            primary = user_selected if (user_selected and user_selected != "auto") else "JavaScript"
            return {}, primary, {}

        # Sort languages by score
        sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_langs[0][0]

        if user_selected and user_selected != "auto" and user_selected.lower() != "other":
            # Map user string (e.g. 'python' -> 'Python')
            for l in EXTENSION_LANGUAGE_MAP.values():
                if l.lower() == user_selected.lower():
                    primary = l
                    break

        total_score = sum(v for _, v in sorted_langs) or 1
        secondary = {l: round((v / total_score) * 100, 1) for l, v in sorted_langs[1:]}

        return lang_counts, primary, secondary

    def _detect_external_dependencies_and_db(
        self, project_root: str, all_files: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str]]:
        """Extract external packages and database ORM indicators."""
        ext_deps: Set[str] = set()
        db_conns: Set[str] = set()
        root_path = Path(project_root)

        # 1. package.json
        pkg_json = root_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for d in list(deps.keys())[:25]:
                    ext_deps.add(d)
                if "prisma" in deps or "@prisma/client" in deps: db_conns.add("Prisma ORM")
                if "mongoose" in deps: db_conns.add("MongoDB (Mongoose)")
                if "pg" in deps or "postgres" in deps: db_conns.add("PostgreSQL (pg)")
                if "mysql" in deps or "mysql2" in deps: db_conns.add("MySQL Driver")
                if "sqlite3" in deps or "better-sqlite3" in deps: db_conns.add("SQLite")
                if "sequelize" in deps: db_conns.add("Sequelize ORM")
                if "typeorm" in deps: db_conns.add("TypeORM")
            except Exception:
                pass

        # 2. requirements.txt / pyproject.toml
        req_txt = root_path / "requirements.txt"
        if req_txt.exists():
            try:
                lines = req_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines:
                    line = line.strip().split("#")[0].split("==")[0].split(">=")[0]
                    if line:
                        ext_deps.add(line.lower())
                        if "sqlalchemy" in line.lower(): db_conns.add("SQLAlchemy ORM")
                        if "psycopg" in line.lower(): db_conns.add("PostgreSQL (psycopg)")
                        if "pymysql" in line.lower(): db_conns.add("MySQL (PyMySQL)")
                        if "sqlite" in line.lower(): db_conns.add("SQLite3")
                        if "pymongo" in line.lower(): db_conns.add("MongoDB (PyMongo)")
                        if "tortoise" in line.lower(): db_conns.add("Tortoise ORM")
            except Exception:
                pass

        # 3. pom.xml
        pom_xml = root_path / "pom.xml"
        if pom_xml.exists():
            try:
                txt = pom_xml.read_text(encoding="utf-8", errors="ignore")
                if "spring-boot-starter-data-jpa" in txt: db_conns.add("Spring Data JPA / Hibernate")
                if "mysql-connector-java" in txt or "mysql-connector-j" in txt: db_conns.add("MySQL JDBC")
                if "postgresql" in txt: db_conns.add("PostgreSQL JDBC")
                if "h2" in txt: db_conns.add("H2 In-Memory DB")
                if "mongodb" in txt: db_conns.add("Spring Data MongoDB")
                for m in re.findall(r"<artifactId>([^<]+)</artifactId>", txt)[:20]:
                    ext_deps.add(m)
            except Exception:
                pass

        # 4. .csproj
        for f in all_files:
            if f["suffix"] == ".csproj":
                try:
                    txt = (root_path / f["rel_path"]).read_text(encoding="utf-8", errors="ignore")
                    if "EntityFramework" in txt or "EntityFrameworkCore" in txt: db_conns.add("Entity Framework Core")
                    if "Npgsql" in txt: db_conns.add("PostgreSQL (Npgsql)")
                    if "SqlClient" in txt: db_conns.add("Microsoft SQL Server")
                    for m in re.findall(r'Include="([^"]+)"', txt)[:15]:
                        ext_deps.add(m)
                except Exception:
                    pass

        return sorted(list(ext_deps)), sorted(list(db_conns))

    def _detect_framework(
        self, project_root: str, all_files: List[Dict[str, Any]], ext_deps: List[str]
    ) -> str:
        """Detect project framework using dependencies and file content samples."""
        deps_str = " ".join(ext_deps).lower()
        if "spring-boot" in deps_str or any("spring" in d for d in ext_deps):
            return "Spring Boot"
        if "fastapi" in deps_str:
            return "FastAPI"
        if "flask" in deps_str:
            return "Flask"
        if "django" in deps_str:
            return "Django"
        if "react" in deps_str or "react-dom" in deps_str:
            return "React"
        if "angular" in deps_str or "@angular/core" in deps_str:
            return "Angular"
        if "vue" in deps_str:
            return "Vue"
        if "express" in deps_str:
            return "Express (Node.js)"
        if "laravel" in deps_str:
            return "Laravel"

        # Check source content samples
        root_path = Path(project_root)
        for f in all_files[:40]:
            if f["suffix"] in [".java", ".py", ".cs", ".js", ".ts", ".php"]:
                try:
                    content = (root_path / f["rel_path"]).read_text(encoding="utf-8", errors="ignore")
                    for fw, patterns in FRAMEWORK_PATTERNS.items():
                        for p in patterns:
                            if re.search(p, content):
                                return fw
                except Exception:
                    continue

        return "Standard / Modular Framework"

    def _detect_project_type(
        self, all_files: List[Dict[str, Any]], framework: str, ext_deps: List[str]
    ) -> str:
        """Classify project type."""
        suffixes = {f["suffix"] for f in all_files}
        names = {f["name"].lower() for f in all_files}

        if any(fw in framework for fw in ["React", "Angular", "Vue"]) or ".html" in suffixes:
            return "Web Application"
        if any(fw in framework for fw in ["FastAPI", "Flask", "Express", "Spring Boot", "Django"]):
            return "API / Web Application"
        if any(f.endswith(".csproj") for f in names) or "electron" in " ".join(ext_deps):
            return "Desktop / API Application"

        return "Web Application"

    def _detect_architecture_and_layers(
        self, all_files: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, List[str]], str]:
        """Classify presentation, business, and data layers."""
        layers: Dict[str, List[str]] = {
            "presentation": [],
            "business": [],
            "data": [],
            "config": []
        }

        for f in all_files:
            path_lower = f["rel_path"].lower()
            suffix = f["suffix"]

            # Presentation layer
            if (any(term in path_lower for term in ["frontend", "views", "components", "controllers", "routes", "pages", "ui", "public", "templates"])
                or suffix in [".html", ".css", ".scss", ".jsx", ".tsx", ".vue"]):
                layers["presentation"].append(f["rel_path"])

            # Business layer
            elif any(term in path_lower for term in ["service", "services", "logic", "domain", "usecase", "manager", "handler"]):
                layers["business"].append(f["rel_path"])

            # Data layer
            elif (any(term in path_lower for term in ["repository", "repositories", "dao", "model", "models", "entity", "entities", "db", "database", "migrations"])
                  or suffix in [".sql"]):
                layers["data"].append(f["rel_path"])

            # Config / Build
            elif (suffix in [".json", ".xml", ".yml", ".yaml", ".ini", ".env", ".toml", ".config"]
                  or f["name"].lower() in ["dockerfile", "makefile"]):
                layers["config"].append(f["rel_path"])

            else:
                # Default fallback heuristic
                if "controller" in path_lower or "route" in path_lower:
                    layers["presentation"].append(f["rel_path"])
                elif "service" in path_lower:
                    layers["business"].append(f["rel_path"])
                else:
                    layers["business"].append(f["rel_path"])

        # Determine architecture pattern
        has_pres = len(layers["presentation"]) > 0
        has_biz = len(layers["business"]) > 0
        has_data = len(layers["data"]) > 0

        if has_pres and has_biz and has_data:
            arch = "Three-Tier Architecture (Presentation, Business, Data)"
        elif has_pres and has_data:
            arch = "Model-View-Controller (MVC)"
        elif has_biz and has_data:
            arch = "Layered Backend Architecture"
        else:
            arch = "Modular / Component-Based Architecture"

        return layers, arch

    def _classify_components(self, all_files: List[Dict[str, Any]]) -> MigrationComponentBreakdown:
        """Classify project components into Controllers, Services, Repositories, Models, DTOs, Entities, etc."""
        cb = MigrationComponentBreakdown()

        for f in all_files:
            path = f["rel_path"]
            name_lower = f["name"].lower()
            path_lower = path.lower()

            if "test" in path_lower or "spec" in path_lower or name_lower.startswith("test_"):
                cb.test_files.append(path)
            elif "controller" in path_lower or "route" in path_lower or "endpoint" in path_lower:
                cb.controllers.append(path)
            elif "service" in path_lower or "usecase" in path_lower or "manager" in path_lower:
                cb.services.append(path)
            elif "repository" in path_lower or "dao" in path_lower:
                cb.repositories.append(path)
            elif "dto" in path_lower or "request" in path_lower or "response" in path_lower or "schema" in path_lower:
                cb.dtos.append(path)
            elif "entity" in path_lower or "entities" in path_lower:
                cb.entities.append(path)
            elif "model" in path_lower:
                cb.models.append(path)
            elif "interface" in path_lower or "protocol" in path_lower:
                cb.interfaces.append(path)
            elif "exception" in path_lower or "error" in path_lower:
                cb.exceptions.append(path)
            elif "util" in path_lower or "helper" in path_lower or "common" in path_lower:
                cb.utilities.append(path)

        return cb

    def _categorize_assets(self, all_files: List[Dict[str, Any]]) -> MigrationAssetCategory:
        """Identify and categorize config files, environment files, auth/security modules, middleware, build & deploy files."""
        ac = MigrationAssetCategory()

        for f in all_files:
            path = f["rel_path"]
            name_lower = f["name"].lower()
            path_lower = path.lower()

            # Environment files
            if ".env" in name_lower or "environment" in name_lower:
                ac.environment_files.append(path)
            # Config files
            elif (f["suffix"] in [".json", ".yml", ".yaml", ".xml", ".properties", ".toml", ".ini", ".config"]
                  and not name_lower.endswith("package.json")):
                ac.config_files.append(path)
            # Auth / Security
            elif any(term in path_lower for term in ["auth", "security", "jwt", "passport", "oauth", "token"]):
                ac.auth_security_modules.append(path)
            # Middleware
            elif "middleware" in path_lower or "interceptor" in path_lower or "filter" in path_lower:
                ac.middleware.append(path)
            # API Routes
            elif "route" in path_lower or "router" in path_lower or "endpoint" in path_lower:
                ac.api_routes.append(path)
            # Static resources
            elif (f["suffix"] in [".css", ".scss", ".png", ".jpg", ".svg", ".ico", ".html"]
                  or "static" in path_lower or "public" in path_lower or "assets" in path_lower):
                ac.static_resources.append(path)
            # Build scripts
            elif (name_lower in ["package.json", "makefile", "build.gradle", "pom.xml", "webpack.config.js", "vite.config.js"]
                  or f["suffix"] in [".sh", ".bat", ".cmd", ".ps1"]):
                ac.build_scripts.append(path)
            # Deployment files
            elif ("docker" in name_lower or "k8s" in path_lower or "kubernetes" in path_lower or ".github" in path_lower or "deploy" in path_lower):
                ac.deployment_files.append(path)

        return ac

    def _detect_entry_points(self, all_files: List[Dict[str, Any]]) -> List[str]:
        """Detect application startup files and main entry points."""
        entry_points = []
        for f in all_files:
            name_lower = f["name"].lower()
            path_lower = f["rel_path"].lower()

            if name_lower in [
                "main.py", "app.py", "server.py", "index.js", "server.js", "app.js",
                "main.js", "main.ts", "app.ts", "program.cs", "startup.cs", "main.go",
                "main.rs", "index.html", "application.java"
            ] or "application" in name_lower or "main" in name_lower:
                entry_points.append(f["rel_path"])

        return entry_points or [f["rel_path"] for f in all_files[:1]]

    def _analyze_internal_dependencies(
        self, project_root: str, all_files: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Extract internal import relationships between files."""
        internal_deps: Dict[str, List[str]] = {}
        file_paths = {f["rel_path"] for f in all_files}
        root_path = Path(project_root)

        for f in all_files[:60]:
            if f["suffix"] in [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".go"]:
                rel = f["rel_path"]
                imports = []
                try:
                    content = (root_path / rel).read_text(encoding="utf-8", errors="ignore")
                    # Match relative imports
                    for match in re.findall(r"(?:import|from|require)\s+['\"](\.[^'\"]+)['\"]", content):
                        imports.append(match)
                    if imports:
                        internal_deps[rel] = imports[:10]
                except Exception:
                    continue

        return internal_deps

    def _filter_scope(
        self,
        all_files: List[Dict[str, Any]],
        scope: str,
        target_path: Optional[str],
        layers: Dict[str, List[str]],
        components: MigrationComponentBreakdown
    ) -> Tuple[List[str], List[str]]:
        """Filter files included and excluded according to migration scope."""
        all_rel_paths = [f["rel_path"] for f in all_files]

        if scope == "file":
            if target_path:
                included = [p for p in all_rel_paths if p.lower() == target_path.lower()]
                if not included:
                    included = all_rel_paths[:1]
            else:
                included = all_rel_paths[:1]
            excluded = [p for p in all_rel_paths if p not in included]

        elif scope == "folder":
            if target_path:
                norm_target = target_path.replace("\\", "/").rstrip("/")
                included = [p for p in all_rel_paths if p.startswith(norm_target)]
            else:
                included = all_rel_paths[:5]
            excluded = [p for p in all_rel_paths if p not in included]

        elif scope == "frontend":
            included = list(set(layers.get("presentation", [])))
            if not included:
                included = [p for p in all_rel_paths if any(ext in p for ext in [".html", ".css", ".js", ".jsx", ".tsx", ".vue"])]
            excluded = [p for p in all_rel_paths if p not in included]

        elif scope == "backend":
            included = list(set(layers.get("business", []) + layers.get("data", [])))
            if not included:
                included = [p for p in all_rel_paths if not any(ext in p for ext in [".html", ".css"])]
            excluded = [p for p in all_rel_paths if p not in included]

        elif scope == "database":
            included = list(set(layers.get("data", []) + components.repositories + components.entities))
            if not included:
                included = [p for p in all_rel_paths if "db" in p.lower() or "model" in p.lower() or "sql" in p.lower()]
            excluded = [p for p in all_rel_paths if p not in included]

        else:  # "project"
            included = all_rel_paths
            excluded = []

        return included, excluded

    def _estimate_complexity(
        self, included_files_count: int, total_loc: int, layers_count: int, ext_deps_count: int, db_conns_count: int
    ) -> str:
        """Estimate migration complexity score."""
        score = 0
        if included_files_count > 10: score += 1
        if included_files_count > 30: score += 1
        if total_loc > 2000: score += 1
        if total_loc > 10000: score += 1
        if layers_count >= 3: score += 1
        if ext_deps_count > 5: score += 1
        if db_conns_count > 0: score += 1

        if score <= 2: return "Low"
        if score <= 4: return "Medium"
        if score <= 6: return "High"
        return "Very High"

    def _generate_markdown_report(self, plan: MigrationPlan, req: MigrationAnalysisRequest) -> str:
        """Generate formatted Markdown Migration Analysis Report."""
        return f"""
# MIGRATION ANALYSIS REPORT

**Project Path:** `{plan.project_path}`
**Analysis Scope:** `{plan.scope.upper()}` {f"(Target: {plan.target_path})" if plan.target_path else ""}
**Source Language:** **{plan.source_language}**
**Target Language:** **{plan.target_language}**
**Project Type:** {plan.project_type}
**Framework:** {plan.framework}
**Architecture Pattern:** {plan.architecture}
**Estimated Complexity:** `{plan.estimated_complexity}`

---

## 1. Executive Summary & Migration Size
- **Total Project Files:** {plan.total_files_count}
- **Files Included in Scope:** **{plan.included_files_count}**
- **Files Excluded from Scope:** {plan.excluded_files_count}
- **Estimated Lines of Code (LOC):** ~{plan.estimated_size_loc:,}
- **Total Migration Volume:** {round(plan.estimated_size_bytes / 1024, 1)} KB

---

## 2. Component Classification
- **Controllers / Routes:** {len(plan.components.controllers)} files
- **Services / Business Logic:** {len(plan.components.services)} files
- **Repositories / DAOs:** {len(plan.components.repositories)} files
- **Models / Schemas:** {len(plan.components.models)} files
- **DTOs:** {len(plan.components.dtos)} files
- **Entities:** {len(plan.components.entities)} files
- **Interfaces:** {len(plan.components.interfaces)} files
- **Utilities / Helpers:** {len(plan.components.utilities)} files
- **Exceptions & Error Handlers:** {len(plan.components.exceptions)} files
- **Test Files:** {len(plan.components.test_files)} files

---

## 3. Key Project Assets & Context
- **Configuration Files:** {len(plan.assets.config_files)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.config_files[:5]]) or "None"})
- **Environment Files:** {len(plan.assets.environment_files)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.environment_files[:3]]) or "None"})
- **Auth & Security Modules:** {len(plan.assets.auth_security_modules)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.auth_security_modules[:3]]) or "None"})
- **Middleware:** {len(plan.assets.middleware)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.middleware[:3]]) or "None"})
- **API Routes:** {len(plan.assets.api_routes)} files
- **Static & UI Assets:** {len(plan.assets.static_resources)} files
- **Build Scripts:** {len(plan.assets.build_scripts)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.build_scripts[:5]]) or "None"})
- **Deployment & Containers:** {len(plan.assets.deployment_files)} ({", ".join([f"`{Path(p).name}`" for p in plan.assets.deployment_files[:5]]) or "None"})

---

## 4. Dependencies & Integrations
- **Database / ORM Connections:** {", ".join([f"**{db}**" for db in plan.database_connections]) or "None detected"}
- **External Libraries ({len(plan.external_dependencies)} detected):**
  {", ".join([f"`{d}`" for d in plan.external_dependencies[:15]]) or "None"}
- **Main Entry Points:**
  {chr(10).join([f"  - `{p}`" for p in plan.entry_points])}

---

## 5. Files Included in Migration Plan ({plan.included_files_count} files)
{chr(10).join([f"- `{p}`" for p in plan.files_included[:25]])}
{f"*(+ {len(plan.files_included) - 25} more files)*" if len(plan.files_included) > 25 else ""}

---

## 6. Next Steps (Phase 3 AI Migration)
> **Ready for AI Code Migration Agent (Phase 3)**
> Structural dependencies, entry points, component classifications, and asset contexts have been indexed. No project source files were modified during this analysis phase.
""".strip()

# Global instance
migration_service = MigrationService()
