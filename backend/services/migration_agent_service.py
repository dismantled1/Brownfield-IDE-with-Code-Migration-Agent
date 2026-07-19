"""
AI Migration Agent — Phase 3 Code Migration Agent
==================================================
Generates migrated code from the Phase 2 Migration Plan using the Phase 0
provider-agnostic AI layer. The agent:

  * REUSES the Phase 2 Migration Plan (it never rescans the project).
  * Talks ONLY through the Provider Interface (get_active_provider) — it never
    imports or calls Ollama / Gemini / Groq / OpenAI / etc. directly.
  * NEVER modifies the original project. Every generated file is written into an
    isolated staging workspace (~/.brownfield-ide/migrations/<session_id>/).
  * Produces per-file diffs (unified + aligned split rows) for a read-only
    comparison view, and a hand-off envelope for Phase 4 (validation),
    Phase 5 (apply) and Phase 6 (integration).

If no AI provider is configured (or a provider errors/times out) the agent falls
back to a deterministic offline translator so the workflow always completes and
the staging workspace / diff view remain populated.
"""

import os
import re
import time
import uuid
import io
import zipfile
import ast
import shutil
import difflib
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.models.schemas import (
    MigrationGenerateRequest,
    MigrationGenerationStatus,
    MigrationGenerationSummary,
    GeneratedFile,
    GeneratedFileMeta,
    GeneratedFileDiffRow,
    MigrationPlan,
)
from backend.services.migration_service import migration_service
from backend.services.llm import get_active_provider

logger = logging.getLogger(__name__)

# Where generated code is staged. This is OUTSIDE the user's project so the
# original project is guaranteed to remain untouched.
import platform
if platform.system() == "Windows":
    _STAGING_ROOT = Path.home() / ".brownfield-ide" / "migrations"
else:
    _STAGING_ROOT = Path("/tmp/.brownfield-ide/migrations")

# Keep prompts bounded so we don't blow past provider context windows.
MAX_SOURCE_CHARS = 12000
# Keep only the most recent N session dirs on disk.
MAX_SESSIONS_ON_DISK = 5

# Target language -> primary source-file extension.
TARGET_EXTENSION_MAP = {
    "java": ".java",
    "python": ".py",
    "csharp": ".cs",
    "c#": ".cs",
    "javascript": ".js",
    "typescript": ".ts",
    "go": ".go",
    "rust": ".rs",
    "cpp": ".cpp",
    "c++": ".cpp",
    "php": ".php",
    "kotlin": ".kt",
    "ruby": ".rb",
    "swift": ".swift",
}

# Human-readable target language names for prompts / reports.
TARGET_DISPLAY_MAP = {
    "java": "Java", "python": "Python", "csharp": "C#", "c#": "C#",
    "javascript": "JavaScript", "typescript": "TypeScript", "go": "Go",
    "rust": "Rust", "cpp": "C++", "c++": "C++", "php": "PHP",
    "kotlin": "Kotlin", "ruby": "Ruby", "swift": "Swift", "other": "Other",
}

# Monaco/Highlight language id per extension (for the diff viewer).
_LANG_ID_MAP = {
    ".py": "python", ".java": "java", ".cs": "csharp", ".js": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".cpp": "cpp", ".c": "c", ".h": "cpp",
    ".php": "php", ".rb": "ruby", ".kt": "kotlin", ".swift": "swift",
    ".html": "html", ".css": "css", ".scss": "scss", ".json": "json",
    ".xml": "xml", ".yml": "yaml", ".yaml": "yaml", ".md": "markdown",
    ".sql": "sql", ".sh": "shell", ".bat": "bat",
}

# Line comment token per target language (offline translator + headers).
_LINE_COMMENT = {
    "java": "//", "csharp": "//", "c#": "//", "javascript": "//",
    "typescript": "//", "go": "//", "rust": "//", "cpp": "//", "c++": "//",
    "php": "//", "kotlin": "//", "swift": "//",
    "python": "#", "ruby": "#",
}

# Binary / non-translatable asset extensions — recorded as "skipped".
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".zip", ".gz", ".tar", ".jar", ".war", ".class", ".exe",
    ".dll", ".so", ".dylib", ".bin", ".mp4", ".mp3", ".wav", ".pyc",
}

# Fixed ordered progress steps (the frontend renders exactly these).
GENERATION_STEPS = [
    "Preparing AI Context",
    "Loading Migration Plan",
    "Loading Provider",
    "Generating Controllers",
    "Generating Services",
    "Generating Repositories",
    "Generating Models",
    "Generating Configuration",
    "Generating Build Files",
    "Building Generated Project",
    "Migration Generation Completed",
]

# Component-type -> which "Generating X" step it belongs to.
_STEP_GROUPS: List[Tuple[str, List[str]]] = [
    ("Generating Controllers", ["controller"]),
    ("Generating Services", ["service", "interface", "utility", "exception", "test", "other"]),
    ("Generating Repositories", ["repository"]),
    ("Generating Models", ["model", "dto", "entity"]),
    ("Generating Configuration", ["config", "static"]),
    ("Generating Build Files", ["build"]),
]


class MigrationAgentService:
    """AI-driven code generator for the Migration Agent (Phase 3)."""

    def __init__(self) -> None:
        self.status = "idle"  # idle, generating, completed, failed
        self.progress = 0.0
        self.current_step = ""
        self.current_file = ""
        self.error_message = ""
        self.step_logs: List[Dict[str, Any]] = []

        self.session_id: Optional[str] = None
        self.staging_path: Optional[str] = None
        self.provider_key: Optional[str] = None
        self.source_language: Optional[str] = None
        self.target_language: Optional[str] = None
        self.source_version: Optional[str] = None
        self.target_version: Optional[str] = None
        self.scope: Optional[str] = None

        # generated_path -> GeneratedFile (full detail, kept in memory)
        self._files: Dict[str, GeneratedFile] = {}
        self._order: List[str] = []  # preserves generation order
        self._handoff: Optional[Dict[str, Any]] = None

        self._lock = asyncio.Lock()
        self._active_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public API (consumed by the router)
    # ------------------------------------------------------------------

    def trigger_generation(self, project_root: str, req: MigrationGenerateRequest) -> None:
        """Start (or restart) background AI code generation."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self._active_task = asyncio.create_task(self.run_generation(project_root, req))

    def get_status(self) -> MigrationGenerationStatus:
        """Return the current generation status with lightweight file metadata."""
        return MigrationGenerationStatus(
            status=self.status,
            progress=round(self.progress, 1),
            current_step=self.current_step,
            current_file=self.current_file,
            step_logs=self.step_logs,
            error=self.error_message or None,
            session_id=self.session_id,
            staging_path=self.staging_path,
            provider=self.provider_key,
            source_language=self.source_language,
            target_language=self.target_language,
            source_version=self.source_version,
            target_version=self.target_version,
            scope=self.scope,
            summary=self._build_summary(),
            files=[self._to_meta(self._files[p]) for p in self._order],
            handoff=self._handoff,
        )

    def get_file(self, generated_path: str) -> Optional[GeneratedFile]:
        """Return the full generated-file payload (content + diff) for one file."""
        norm = (generated_path or "").replace("\\", "/").strip("/")
        return self._files.get(norm)

    def all_generated_files(self) -> List[GeneratedFile]:
        """Return all generated files in generation order (read-only accessor)."""
        return [self._files[p] for p in self._order]

    def get_project_zip(self) -> Tuple[bytes, str, int]:
        """Generate a ZIP archive in memory containing all generated files in staging."""
        if not self.staging_path or not os.path.exists(self.staging_path):
            raise MigrationAgentError("No generated migration workspace available for download.")

        staging = Path(self.staging_path)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(staging):
                for file in files:
                    full_p = Path(root) / file
                    rel_p = full_p.relative_to(staging)
                    zf.write(full_p, arcname=str(rel_p).replace("\\", "/"))

        zip_bytes = buffer.getvalue()
        filename = f"migrated_project_{self.session_id or 'output'}.zip"
        return zip_bytes, filename, len(zip_bytes)

    def get_folder_zip(self, folder_path: str) -> Tuple[bytes, str, int]:
        """Generate a ZIP archive of a specific folder in the staging workspace."""
        if not self.staging_path or not os.path.exists(self.staging_path):
            raise MigrationAgentError("No generated migration workspace available for download.")

        staging = Path(self.staging_path)
        norm_dir = (folder_path or "").replace("\\", "/").strip("/")
        target_dir = (staging / norm_dir).resolve() if norm_dir else staging
        if not target_dir.exists() or not target_dir.is_dir():
            target_dir = staging

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(target_dir):
                for file in files:
                    full_p = Path(root) / file
                    rel_p = full_p.relative_to(target_dir)
                    zf.write(full_p, arcname=str(rel_p).replace("\\", "/"))

        zip_bytes = buffer.getvalue()
        folder_name = Path(norm_dir).name if norm_dir else "project"
        filename = f"migrated_{folder_name}_{self.session_id or 'output'}.zip"
        return zip_bytes, filename, len(zip_bytes)

    def get_file_zip(self, file_path: str) -> Tuple[bytes, str, int]:
        """Generate a ZIP archive containing a single generated file."""
        norm_path = (file_path or "").replace("\\", "/").strip("/")
        gf = self.get_file(norm_path)
        if not gf:
            # try finding by generated_path matching
            gf = next((f for f in self._files.values() if f.generated_path.endswith(norm_path) or norm_path.endswith(f.generated_path)), None)

        if not gf or not self.staging_path:
            raise MigrationAgentError(f"Generated file not found: {file_path}")

        full_p = Path(self.staging_path) / gf.generated_path
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if full_p.exists():
                zf.write(full_p, arcname=gf.generated_path)
            else:
                zf.writestr(gf.generated_path, gf.generated_content)

        zip_bytes = buffer.getvalue()
        filename_base = Path(gf.generated_path).stem
        filename = f"migrated_{filename_base}_{self.session_id or 'file'}.zip"
        return zip_bytes, filename, len(zip_bytes)

    def get_download_info(self, download_type: str = "project", path: Optional[str] = None) -> Dict[str, Any]:
        """Compute file count, total uncompressed size, and ZIP size for previewing in UI."""
        if not self.staging_path or not os.path.exists(self.staging_path):
            return {
                "success": False,
                "message": "No generated migration available.",
                "file_count": 0,
                "total_bytes": 0,
                "zip_size_bytes": 0,
                "formatted_zip_size": "0 KB",
                "staging_path": self.staging_path,
            }

        try:
            if download_type == "file" and path:
                b, fn, sz = self.get_file_zip(path)
                cnt = 1
            elif download_type == "folder" and path:
                b, fn, sz = self.get_folder_zip(path)
                cnt = sum(1 for p in self._files if p.startswith(path)) or len(self._files)
            else:
                b, fn, sz = self.get_project_zip()
                cnt = len(self._files)

            fmt_size = f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024 * 1024):.2f} MB"
            return {
                "success": True,
                "type": download_type,
                "path": path,
                "filename": fn,
                "file_count": cnt,
                "zip_size_bytes": sz,
                "formatted_zip_size": fmt_size,
                "staging_path": self.staging_path,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "staging_path": self.staging_path,
            }

    def get_handoff(self) -> Optional[Dict[str, Any]]:
        return self._handoff

    def reset(self) -> None:
        """Clear the in-memory session state (does not delete staged files)."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self.status = "idle"
        self.progress = 0.0
        self.current_step = ""
        self.current_file = ""
        self.error_message = ""
        self.step_logs = []
        self.session_id = None
        self.staging_path = None
        self.provider_key = None
        self.source_language = None
        self.target_language = None
        self.scope = None
        self._files = {}
        self._order = []
        self._handoff = None

    # ------------------------------------------------------------------
    # Core generation pipeline
    # ------------------------------------------------------------------

    async def run_generation(self, project_root: str, req: MigrationGenerateRequest) -> None:
        async with self._lock:
            try:
                self._reset_run_state(req)

                project_path = Path(project_root).resolve()

                # --- Step 1: Preparing AI Context ---------------------------------
                self._log_step(3.0, "Preparing AI Context",
                               "Assembling migration context (no project rescan).")
                await asyncio.sleep(0.05)

                # --- Step 2: Loading Migration Plan (reuse Phase 2 output) --------
                plan = migration_service.active_plan
                if plan is None:
                    raise MigrationAgentError(
                        "No Migration Plan available. Run Migration Analysis "
                        "(Phase 2) before generating code."
                    )
                self._log_step(8.0, "Loading Migration Plan",
                               f"Reusing plan: {plan.included_files_count} files in "
                               f"'{plan.scope}' scope, {plan.source_language} → "
                               f"{self.target_language}.")
                await asyncio.sleep(0.05)

                # Validate target language support (graceful, not fatal).
                target_ext = self._target_extension(req.target_lang)
                if target_ext is None:
                    self._log_step(self.progress, "Loading Migration Plan",
                                   f"⚠ Unsupported target language '{req.target_lang}'. "
                                   f"Generated files will use a .txt extension.")

                # Framework support note (informational only).
                if plan.framework in ("Unknown", "", "Standard / Modular Framework"):
                    self._log_step(self.progress, "Loading Migration Plan",
                                   "⚠ Source framework not confidently detected — "
                                   "translating with generic conventions.")

                # --- Step 3: Loading Provider (via Provider Interface only) -------
                provider = get_active_provider()
                if provider is not None:
                    self.provider_key = provider.key
                    self._log_step(12.0, "Loading Provider",
                                   f"Active provider: {provider.key} (model: {provider.model}).")
                else:
                    self.provider_key = "offline"
                    self._log_step(12.0, "Loading Provider",
                                   "No AI provider configured — using offline "
                                   "deterministic translator.")
                await asyncio.sleep(0.05)

                # --- Prepare staging workspace ------------------------------------
                self._prepare_staging_workspace()

                # --- Build ordered work list from the plan ------------------------
                work_items = self._build_work_items(plan, req, target_ext)

                # --- Steps 4-9: Generate code by component group ------------------
                await self._generate_all(project_path, plan, req, provider, work_items, target_ext)

                # --- Step 10: Building Generated Project --------------------------
                self._log_step(95.0, "Building Generated Project",
                               f"Assembled {len(self._order)} file(s) in staging workspace.")
                await asyncio.sleep(0.05)
                self._handoff = self._build_handoff(plan)

                # --- Step 11: Completed ------------------------------------------
                summary = self._build_summary()
                self._log_step(
                    100.0, "Migration Generation Completed",
                    f"Done. {summary.new_files} new, {summary.modified_files} modified, "
                    f"{summary.skipped_files} skipped, {summary.failed_files} failed."
                )
                self.status = "completed"

            except asyncio.CancelledError:
                logger.info("Migration generation cancelled.")
                self.status = "idle"
                raise
            except MigrationAgentError as exc:
                logger.warning(f"Migration generation aborted: {exc}")
                self.status = "failed"
                self.error_message = str(exc)
                self._log_step(self.progress, "Generation Failed", f"Error: {exc}")
            except Exception as exc:  # noqa: BLE001 — surface any failure cleanly
                logger.error(f"Migration generation failed: {exc}", exc_info=True)
                self.status = "failed"
                self.error_message = str(exc)
                self._log_step(self.progress, "Generation Failed", f"Unexpected error: {exc}")

    async def _generate_all(
        self,
        project_path: Path,
        plan: MigrationPlan,
        req: MigrationGenerateRequest,
        provider,
        work_items: List[Dict[str, Any]],
        target_ext: Optional[str],
    ) -> None:
        """Iterate component groups, generating (or skipping) each file."""
        total = len(work_items)
        done = 0
        force_offline = provider is None
        provider_ever_succeeded = False
        warned_unavailable = False

        # Which component types actually have work (so we can log every step even
        # when a group is empty — the UI shows the full checklist).
        types_present = {w["component_type"] for w in work_items}

        for step_name, comp_types in _STEP_GROUPS:
            group_items = [w for w in work_items if w["component_type"] in comp_types]
            has_group_work = any(t in types_present for t in comp_types)

            if not group_items:
                # Log the step so the UI can tick it off, then move on.
                self._log_step(
                    self._file_progress(done, total), step_name,
                    "No files of this type in the selected scope."
                    if not has_group_work else "Skipped."
                )
                continue

            self._log_step(self._file_progress(done, total), step_name,
                           f"Generating {len(group_items)} file(s)…")

            for item in group_items:
                self.current_step = step_name
                self.current_file = item["rel_path"]

                gen_file, outcome, err = await self._generate_one(
                    project_path, plan, req, provider, item, target_ext,
                    force_offline=force_offline,
                )

                if outcome == "provider_ok":
                    provider_ever_succeeded = True
                elif outcome == "provider_error":
                    if provider_ever_succeeded:
                        # Provider worked earlier → this is a genuine per-file
                        # failure (context limit, malformed output, timeout).
                        gen_file.status = "failed"
                        gen_file.error = err
                    else:
                        # Provider never worked → treat it as unreachable and run
                        # the rest of the batch offline (one warning, clean run).
                        force_offline = True
                        # Reflect what actually generated the code in the run-level
                        # provider label (the configured provider was unreachable).
                        self.provider_key = "offline"
                        if not warned_unavailable:
                            warned_unavailable = True
                            self._log_step(
                                self._file_progress(done, total), step_name,
                                f"⚠ AI provider unreachable ({err}). Generating this "
                                f"run with the offline deterministic translator."
                            )

                self._record_file(gen_file)
                done += 1
                self.progress = self._file_progress(done, total)
                # Yield control so status polling stays responsive.
                await asyncio.sleep(0)

    async def _generate_one(
        self,
        project_path: Path,
        plan: MigrationPlan,
        req: MigrationGenerateRequest,
        provider,
        item: Dict[str, Any],
        target_ext: Optional[str],
        force_offline: bool,
    ) -> Tuple[GeneratedFile, str, Optional[str]]:
        """Generate (or skip) a single file.

        Returns (GeneratedFile, outcome, error) where outcome is one of
        "provider_ok", "provider_error", "offline", or "skipped". The caller
        (``_generate_all``) decides the final status for provider errors so a
        never-reachable provider yields a clean offline run instead of failures.
        """
        rel_path = item["rel_path"]
        component_type = item["component_type"]
        gen_rel_path = item["gen_rel_path"]
        gen_lang = _LANG_ID_MAP.get(Path(gen_rel_path).suffix.lower(), "plaintext")

        # Skip files flagged during work-item construction (binary / over cap).
        if item.get("skip_reason"):
            return (
                GeneratedFile(
                    original_path=rel_path, generated_path=gen_rel_path,
                    component_type=component_type, language=gen_lang,
                    status="skipped", provider="n/a", reason=item["skip_reason"],
                ),
                "skipped", None,
            )

        original = self._read_source(project_path / rel_path)
        if original is None:
            return (
                GeneratedFile(
                    original_path=rel_path, generated_path=gen_rel_path,
                    component_type=component_type, language=gen_lang,
                    status="skipped", provider="n/a",
                    reason="Source file unreadable or missing.",
                ),
                "skipped", None,
            )

        truncated = len(original) > MAX_SOURCE_CHARS
        source_for_prompt = original[:MAX_SOURCE_CHARS]
        reason: Optional[str] = "Source truncated to fit context window." if truncated else None

        generated: Optional[str] = None
        error: Optional[str] = None
        if provider is not None and not force_offline:
            try:
                prompt, system = self._build_prompt(plan, req, rel_path, component_type, source_for_prompt)
                result = await asyncio.to_thread(provider.generate, prompt, system=system)
                if result.ok and result.text and result.text.strip():
                    generated = self._strip_fences(result.text)
                else:
                    error = result.error or "empty response"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

        if generated is not None:
            # Clean AI translation.
            self._write_to_staging(gen_rel_path, generated)
            gen_file = self._finalize_file(
                rel_path, gen_rel_path, component_type, gen_lang,
                original, generated, provider.key, reason=reason,
            )
            return gen_file, "provider_ok", None

        # Offline deterministic fallback (no provider, forced offline, or error).
        generated = self._offline_translate(original, plan, req, rel_path, component_type)
        self._write_to_staging(gen_rel_path, generated)
        gen_file = self._finalize_file(
            rel_path, gen_rel_path, component_type, gen_lang,
            original, generated, "offline", reason=reason,
        )
        outcome = "provider_error" if error else "offline"
        return gen_file, outcome, error

    # ------------------------------------------------------------------
    # Work-item construction (reuses Phase 2 plan; no rescan)
    # ------------------------------------------------------------------

    def _build_work_items(
        self, plan: MigrationPlan, req: MigrationGenerateRequest, target_ext: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Turn plan.files_included into an ordered, classified work list.

        Ordering follows _STEP_GROUPS so the most important code (controllers,
        services…) is generated first and survives the max_files cap; assets and
        build files come last.
        """
        included = list(dict.fromkeys(plan.files_included))  # de-dupe, keep order

        classified: List[Dict[str, Any]] = []
        for rel in included:
            ctype = self._classify_path(plan, rel)
            classified.append({"rel_path": rel, "component_type": ctype})

        # Sort by group order, then path.
        group_rank = {}
        for idx, (_, types) in enumerate(_STEP_GROUPS):
            for t in types:
                group_rank[t] = idx
        classified.sort(key=lambda w: (group_rank.get(w["component_type"], 99), w["rel_path"]))

        # Apply the translation cap; overflow becomes skipped (still listed).
        code_budget = req.max_files
        translated = 0
        for w in classified:
            rel = w["rel_path"]
            ext = Path(rel).suffix.lower()
            w["gen_rel_path"] = self._remap_path(rel, ext, target_ext)

            if ext in _BINARY_EXTS:
                w["skip_reason"] = "Binary/asset file — not translated."
                continue
            if translated >= code_budget:
                w["skip_reason"] = (
                    f"Exceeds max file batch ({code_budget}). "
                    "Increase 'max files' to include it."
                )
                continue
            translated += 1

        return classified

    def _classify_path(self, plan: MigrationPlan, path: str) -> str:
        c = plan.components
        a = plan.assets
        if path in c.controllers:
            return "controller"
        if path in c.services:
            return "service"
        if path in c.interfaces:
            return "interface"
        if path in c.repositories:
            return "repository"
        if path in c.entities:
            return "entity"
        if path in c.dtos:
            return "dto"
        if path in c.models:
            return "model"
        if path in c.utilities:
            return "utility"
        if path in c.exceptions:
            return "exception"
        if path in c.test_files:
            return "test"
        if path in a.build_scripts or path in a.deployment_files:
            return "build"
        if path in a.config_files or path in a.environment_files:
            return "config"
        if path in a.static_resources:
            return "static"
        if path in a.api_routes:
            return "controller"
        if path in a.middleware or path in a.auth_security_modules:
            return "service"
        return "other"

    # ------------------------------------------------------------------
    # Prompt construction (Provider Interface input)
    # ------------------------------------------------------------------

    def _build_prompt(
        self, plan: MigrationPlan, req: MigrationGenerateRequest,
        rel_path: str, component_type: str, source: str,
    ) -> Tuple[str, str]:
        target_lang_str = req.target_language or req.target_lang or "java"
        target_display = self._target_display(target_lang_str)
        strategies = ", ".join(req.strategies) if req.strategies else "preserve architecture, structure & naming"
        deps = ", ".join(plan.external_dependencies[:15]) or "none detected"
        dbs = ", ".join(plan.database_connections) or "none detected"

        src_v = req.source_version or (plan.source_version if plan else None)
        tgt_v = req.target_version or (plan.target_version if plan else None)
        ver_prompt = ""
        if src_v or tgt_v:
            ver_prompt = (
                f"\n- LANGUAGE VERSION TARGET: Upgrade from {plan.source_language} ({src_v or 'legacy'}) "
                f"to {target_display} ({tgt_v or 'latest'}). Modernize syntax, language idioms, APIs, and project structure "
                f"to conform with {target_display} {tgt_v or 'latest'} standards while preserving all business logic."
            )

        system = (
            "You are an expert software migration engineer. You translate source "
            "code from one language/framework/version to another while preserving behavior, "
            "architecture, folder structure, naming conventions, layer "
            "relationships, configuration structure and business logic. "
            "Output ONLY the complete translated file content. Do NOT include "
            "markdown code fences, explanations, or commentary."
        )
        prompt = (
            f"Migrate the following {plan.source_language} file to {target_display}.\n\n"
            f"PROJECT CONTEXT (from static analysis — do not rescan):\n"
            f"- Project type: {plan.project_type}\n"
            f"- Source framework: {plan.framework}\n"
            f"- Architecture: {plan.architecture}\n"
            f"- Component type: {component_type}\n"
            f"- Migration strategy: {strategies}\n"
            f"- External dependencies (map to {target_display} equivalents where needed): {deps}\n"
            f"- Database / ORM: {dbs}\n\n"
            f"REQUIREMENTS:\n"
            f"- Preserve the original architecture, folder/module structure and naming.\n"
            f"- Keep the same public behavior and business logic.\n"
            f"- Produce idiomatic, compilable {target_display} for a '{component_type}' component.{ver_prompt}\n\n"
            f"Original file path: {rel_path}\n\n"
            f"--- ORIGINAL {plan.source_language.upper()} CODE ---\n"
            f"{source}\n"
            f"--- END ORIGINAL CODE ---\n\n"
            f"Return the complete migrated {target_display} file content only."
        )
        return prompt, system

    # ------------------------------------------------------------------
    # Offline deterministic translator (fallback)
    # ------------------------------------------------------------------

    def _offline_translate(
        self, original: str, plan: MigrationPlan, req: MigrationGenerateRequest,
        rel_path: str, component_type: str,
    ) -> str:
        target = (req.target_language or req.target_lang or "java").lower()
        target_display = self._target_display(target)
        src_v = req.source_version or (plan.source_version if plan else None)
        tgt_v = req.target_version or (plan.target_version if plan else None)
        ver_info = f" (v{src_v} -> v{tgt_v})" if (src_v and tgt_v) else (f" (v{tgt_v})" if tgt_v else "")

        cmt = _LINE_COMMENT.get(target, "//")
        header = (
            f"{cmt} ============================================================\n"
            f"{cmt} MIGRATED FILE (offline deterministic stub)\n"
            f"{cmt} {plan.source_language} -> {target_display}{ver_info}\n"
            f"{cmt} Source: {rel_path}\n"
            f"{cmt} Component: {component_type}\n"
            f"{cmt} Framework: {plan.framework} | Architecture: {plan.architecture}\n"
            f"{cmt} NOTE: Configure an AI provider (Phase 0 settings) for a full\n"
            f"{cmt}       AI-generated translation. The original source is preserved\n"
            f"{cmt}       below as reference comments.\n"
            f"{cmt} ============================================================\n\n"
        )
        body = "\n".join(f"{cmt} {line}" for line in original.splitlines())
        return header + body + "\n"

    # ------------------------------------------------------------------
    # Syntax verification and auto-fix
    # ------------------------------------------------------------------

    def _verify_and_autofix_syntax(self, content: str, gen_lang: str) -> str:
        """Validate syntactical correctness and attempt auto-fix for fence leaks or malformed headers."""
        if not content or not content.strip():
            return content
        
        cleaned = self._strip_fences(content)
        lang = (gen_lang or "").lower()

        if lang in ("python", "py"):
            try:
                ast.parse(cleaned)
                return cleaned
            except SyntaxError:
                # Attempt syntax cleanup if fences or stray characters remained
                lines = cleaned.splitlines()
                filtered = [l for l in lines if not l.strip().startswith("```")]
                try:
                    candidate = "\n".join(filtered) + "\n"
                    ast.parse(candidate)
                    return candidate
                except SyntaxError:
                    return cleaned

        return cleaned

    # ------------------------------------------------------------------
    # Diff computation
    # ------------------------------------------------------------------

    def _finalize_file(
        self, rel_path: str, gen_rel_path: str, component_type: str, gen_lang: str,
        original: str, generated: str, provider: str,
        status_override: Optional[str] = None, error: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> GeneratedFile:
        generated = self._verify_and_autofix_syntax(generated, gen_lang)
        unified, rows, additions, removals = self._compute_diff(gen_rel_path, original, generated)
        if status_override:
            status = status_override
        elif not original.strip() or gen_rel_path != rel_path:
            # Remapped to a new target-language file (or no original) → NEW file.
            status = "new"
        else:
            # Same path, content changed in place → MODIFIED file.
            status = "modified"
        return GeneratedFile(
            original_path=rel_path,
            generated_path=gen_rel_path,
            component_type=component_type,
            language=gen_lang,
            status=status,
            provider=provider,
            additions=additions,
            removals=removals,
            error=error,
            reason=reason,
            original_content=original,
            generated_content=generated,
            diff=unified,
            diff_rows=rows,
        )

    def _compute_diff(
        self, path_label: str, before: str, after: str
    ) -> Tuple[str, List[GeneratedFileDiffRow], int, int]:
        before_lines = before.splitlines()
        after_lines = after.splitlines()

        # Unified diff text.
        ud = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path_label}" if before else "/dev/null",
            tofile=f"b/{path_label}",
            lineterm="",
        )
        unified = "".join(l if l.endswith("\n") else l + "\n" for l in ud)

        # Aligned split rows via opcodes.
        rows: List[GeneratedFileDiffRow] = []
        additions = removals = 0
        sm = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    rows.append(GeneratedFileDiffRow(
                        type="equal",
                        left_num=i1 + k + 1, right_num=j1 + k + 1,
                        left=before_lines[i1 + k], right=after_lines[j1 + k],
                    ))
            elif tag == "delete":
                for k in range(i2 - i1):
                    removals += 1
                    rows.append(GeneratedFileDiffRow(
                        type="remove", left_num=i1 + k + 1, left=before_lines[i1 + k],
                    ))
            elif tag == "insert":
                for k in range(j2 - j1):
                    additions += 1
                    rows.append(GeneratedFileDiffRow(
                        type="add", right_num=j1 + k + 1, right=after_lines[j1 + k],
                    ))
            elif tag == "replace":
                la, lb = i2 - i1, j2 - j1
                for k in range(max(la, lb)):
                    left = before_lines[i1 + k] if k < la else None
                    right = after_lines[j1 + k] if k < lb else None
                    if left is not None and right is not None:
                        additions += 1
                        removals += 1
                        rows.append(GeneratedFileDiffRow(
                            type="modify",
                            left_num=i1 + k + 1, right_num=j1 + k + 1,
                            left=left, right=right,
                        ))
                    elif left is not None:
                        removals += 1
                        rows.append(GeneratedFileDiffRow(
                            type="remove", left_num=i1 + k + 1, left=left,
                        ))
                    else:
                        additions += 1
                        rows.append(GeneratedFileDiffRow(
                            type="add", right_num=j1 + k + 1, right=right,
                        ))
        return unified, rows, additions, removals

    # ------------------------------------------------------------------
    # Staging workspace (isolated — never the original project)
    # ------------------------------------------------------------------

    def _prepare_staging_workspace(self) -> None:
        self.session_id = uuid.uuid4().hex[:12]
        staging = _STAGING_ROOT / self.session_id
        staging.mkdir(parents=True, exist_ok=True)
        self.staging_path = str(staging)
        self._prune_old_sessions()

    def _write_to_staging(self, gen_rel_path: str, content: str) -> None:
        if not self.staging_path:
            return
        # Guard against path traversal — everything stays under the staging dir.
        staging_root = Path(self.staging_path).resolve()
        target = (staging_root / gen_rel_path).resolve()
        try:
            target.relative_to(staging_root)
        except ValueError:
            logger.warning(f"Refusing to write outside staging: {gen_rel_path}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _prune_old_sessions(self) -> None:
        try:
            if not _STAGING_ROOT.exists():
                return
            sessions = [d for d in _STAGING_ROOT.iterdir() if d.is_dir()]
            sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            for old in sessions[MAX_SESSIONS_ON_DISK:]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Session prune skipped: {exc}")

    # ------------------------------------------------------------------
    # Hand-off envelope for later phases (Phase 4 / 5 / 6)
    # ------------------------------------------------------------------

    def _build_handoff(self, plan: MigrationPlan) -> Dict[str, Any]:
        summary = self._build_summary()
        files = [{
            "original_path": f.original_path,
            "generated_path": f.generated_path,
            "component_type": f.component_type,
            "language": f.language,
            "status": f.status,
            "additions": f.additions,
            "removals": f.removals,
        } for f in (self._files[p] for p in self._order)]

        return {
            "session_id": self.session_id,
            "staging_path": self.staging_path,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "scope": self.scope,
            "provider": self.provider_key,
            "summary": summary.model_dump(),
            "files": files,
            # Extension points — later phases read this envelope. Nothing here
            # applies or validates anything yet.
            "next_phase": {
                "phase4_validation": {
                    "ready_for_validation": summary.failed_files == 0,
                    "generated_root": self.staging_path,
                    "files_to_validate": [f["generated_path"] for f in files
                                          if f["status"] in ("new", "modified")],
                },
                "phase5_apply": {
                    "ready": False,
                    "requires_approval": True,
                    "applied": False,
                    "staging_path": self.staging_path,
                    "original_project": plan.project_path,
                },
                "phase6_integration": {
                    "ready": False,
                    "notes": "Awaiting Phase 4 validation and Phase 5 apply.",
                },
            },
        }

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _reset_run_state(self, req: MigrationGenerateRequest) -> None:
        self.status = "generating"
        self.progress = 0.0
        self.current_step = ""
        self.current_file = ""
        self.error_message = ""
        self.step_logs = []
        self.session_id = None
        self.staging_path = None
        self.provider_key = None
        plan = migration_service.active_plan
        self.scope = req.scope
        target_lang = req.target_language or req.target_lang
        self.target_language = self._target_display(target_lang)
        self.source_language = plan.source_language if plan else (req.source_language or req.source_lang or "Unknown")
        self.source_version = req.source_version or (plan.source_version if plan else None)
        self.target_version = req.target_version or (plan.target_version if plan else None)
        self._files = {}
        self._order = []
        self._handoff = None

    def _record_file(self, gen_file: GeneratedFile) -> None:
        key = gen_file.generated_path
        if key not in self._files:
            self._order.append(key)
        self._files[key] = gen_file

    def _log_step(self, progress: float, step_name: str, detail: str) -> None:
        self.progress = progress
        self.current_step = step_name
        self.step_logs.append({
            "step": step_name,
            "detail": detail,
            "progress": round(progress, 1),
            "timestamp": time.strftime("%H:%M:%S"),
        })

    @staticmethod
    def _file_progress(done: int, total: int) -> float:
        # File generation spans 15% -> 90%.
        if total <= 0:
            return 90.0
        return 15.0 + (done / total) * 75.0

    def _build_summary(self) -> MigrationGenerationSummary:
        files = [self._files[p] for p in self._order]
        new = sum(1 for f in files if f.status == "new")
        modified = sum(1 for f in files if f.status == "modified")
        skipped = sum(1 for f in files if f.status == "skipped")
        failed = sum(1 for f in files if f.status == "failed")
        warnings = sum(1 for f in files if f.reason) + skipped
        return MigrationGenerationSummary(
            files_selected=len(files),
            files_generated=new + modified,
            new_files=new,
            modified_files=modified,
            skipped_files=skipped,
            failed_files=failed,
            warnings=warnings,
            errors=failed,
            additions=sum(f.additions for f in files),
            removals=sum(f.removals for f in files),
        )

    @staticmethod
    def _to_meta(f: GeneratedFile) -> GeneratedFileMeta:
        return GeneratedFileMeta(
            original_path=f.original_path,
            generated_path=f.generated_path,
            component_type=f.component_type,
            language=f.language,
            status=f.status,
            provider=f.provider,
            additions=f.additions,
            removals=f.removals,
            error=f.error,
            reason=f.reason,
        )

    @staticmethod
    def _read_source(path: Path) -> Optional[str]:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
        return None

    @staticmethod
    def _target_extension(target_lang: Optional[str]) -> Optional[str]:
        return TARGET_EXTENSION_MAP.get((target_lang or "").lower())

    @staticmethod
    def _target_display(target_lang: Optional[str]) -> str:
        key = (target_lang or "java").lower()
        return TARGET_DISPLAY_MAP.get(key, (target_lang or "Java").capitalize())

    def _remap_path(self, rel_path: str, ext: str, target_ext: Optional[str]) -> str:
        """Map an original file path to its generated counterpart.

        Source-code files get the target-language extension; everything else
        (config, assets, build files) keeps its original path so the staging
        workspace mirrors the original folder hierarchy.
        """
        rel = rel_path.replace("\\", "/")
        # Only remap actual source-code extensions.
        code_exts = set(_LANG_ID_MAP.keys()) - {
            ".html", ".css", ".scss", ".json", ".xml", ".yml", ".yaml",
            ".md", ".sql", ".sh", ".bat",
        }
        if target_ext and ext in code_exts:
            return str(Path(rel).with_suffix(target_ext)).replace("\\", "/")
        if target_ext is None and ext in code_exts:
            return str(Path(rel).with_suffix(".txt")).replace("\\", "/")
        return rel

    @staticmethod
    def _strip_fences(text: str) -> str:
        cleaned = text.strip()
        # Remove a leading ```lang fence and trailing ``` fence if present.
        cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        return cleaned.strip("\n") + "\n"


class MigrationAgentError(Exception):
    """Raised for recoverable, user-facing generation errors."""


# Global singleton instance
migration_agent_service = MigrationAgentService()
