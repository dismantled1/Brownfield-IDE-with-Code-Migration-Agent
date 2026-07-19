"""
Migration Orchestrator Service — Phase 6: Final Integration & Workflow Orchestration
=====================================================================================
Central controller that orchestrates all completed migration phases:

  * Phase 2: Migration Analysis Engine (migration_service)
  * Phase 3: AI Migration Agent (migration_agent_service)
  * Phase 4: Migration Validation & Review (migration_validation_service)
  * Phase 5: Apply Migration & Rollback Engine (migration_apply_service)

Provides live step logs, unified dashboard stats, automated phase transitions,
error resilience, workflow recovery, and historical report reopening.
"""

from __future__ import annotations

import os
import json
import time
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.models.schemas import (
    WorkflowStartRequest,
    WorkflowStepLog,
    WorkflowStatusResponse,
    UnifiedDashboardResponse,
    ArchivedMigrationReport,
    MigrationAnalysisRequest,
    MigrationGenerateRequest,
)
from backend.services.workspace_service import get_current_project
from backend.services.llm.config import config_manager
from backend.services.llm import get_active_provider
from backend.services.migration_service import migration_service
from backend.services.migration_agent_service import migration_agent_service
from backend.services.migration_validation_service import migration_validation_service
from backend.services.migration_apply_service import migration_apply_service

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    """Central engine controlling the complete Code Migration lifecycle."""

    def __init__(self) -> None:
        self.workflow_id: str = str(uuid.uuid4())[:8]
        self.state: str = "idle"  # idle, analyzing, generating, validating, approved, applying, completed, failed, rolled_back
        self.global_progress: float = 0.0
        self.current_phase: str = ""
        self.current_step: str = ""
        self.error_message: str = ""
        
        self.step_logs: List[WorkflowStepLog] = []
        self._start_time: float = time.time()
        self._step_start_time: float = time.time()

        self._lock = asyncio.Lock()
        self._active_task: Optional[asyncio.Task] = None

    def log_step(
        self,
        phase: str,
        step: str,
        status: str = "info",
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a timestamped execution log entry for the Live Execution Console."""
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        duration = round(time.time() - self._step_start_time, 2)
        self._step_start_time = time.time()

        log_entry = WorkflowStepLog(
            timestamp=now_str,
            phase=phase,
            step=step,
            duration_s=duration,
            status=status,
            message=message or f"{step} ({status})",
            details=details,
        )
        self.step_logs.append(log_entry)
        self.current_phase = phase
        self.current_step = step
        logger.info(f"[{phase}] {step} ({status}): {message}")

    def trigger_workflow(self, req: WorkflowStartRequest) -> None:
        """Initiate or restart background workflow execution."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        
        self.workflow_id = str(uuid.uuid4())[:8]
        self.state = "analyzing"
        self.global_progress = 0.0
        self.error_message = ""
        self.step_logs.clear()
        self._start_time = time.time()
        self._step_start_time = time.time()

        project_path = get_current_project() or str(Path.cwd())
        self._active_task = asyncio.create_task(self.run_workflow(project_path, req))

    async def run_workflow(self, project_path: str, req: WorkflowStartRequest) -> None:
        """Execute all migration phases in an orchestrated, resilient flow."""
        async with self._lock:
            try:
                self.log_step("Platform", "Workflow Initialized", "running", f"Targeting {req.target_lang} for scope '{req.scope}'")
                
                # -------------------------------------------------------------
                # Phase 1: Environment & Provider Diagnostics
                # -------------------------------------------------------------
                self.global_progress = 5.0
                active_llm = get_active_provider()
                provider_name = active_llm.key if active_llm else "offline"
                model_name = active_llm.model if active_llm else "deterministic-translator"
                ollama_ok = config_manager.is_ollama_installed()
                
                self.log_step(
                    "AI Provider",
                    f"AI Layer Ready ({provider_name})",
                    "success" if active_llm else "warning",
                    f"Active provider: '{provider_name}', Model: '{model_name}', Ollama installed: {ollama_ok}"
                )

                # -------------------------------------------------------------
                # Phase 2: Migration Analysis Engine
                # -------------------------------------------------------------
                self.state = "analyzing"
                self.global_progress = 15.0
                self.log_step("Phase 2", "Project Analysis Initiated", "running", "Scanning architecture, frameworks, and component breakdown")

                analysis_req = MigrationAnalysisRequest(
                    scope=req.scope,
                    target_path=req.target_path,
                    source_lang=req.source_lang,
                    target_lang=req.target_lang,
                    source_language=req.source_language,
                    target_language=req.target_language,
                    source_version=req.source_version,
                    target_version=req.target_version,
                    strategies=req.strategies or [],
                )
                
                await migration_service.run_analysis(project_path, analysis_req)
                plan = migration_service.active_plan
                
                if not plan:
                    raise RuntimeError("Phase 2 Migration Analysis produced no plan.")

                self.global_progress = 30.0
                self.log_step(
                    "Phase 2",
                    "Migration Plan Generated",
                    "success",
                    f"Source: {plan.source_language}, Framework: {plan.framework}, Total Files: {plan.total_files_count}, Included: {plan.included_files_count}"
                )

                # -------------------------------------------------------------
                # Phase 3: AI Migration Agent Code Generation
                # -------------------------------------------------------------
                self.state = "generating"
                self.global_progress = 40.0
                self.log_step("Phase 3", "AI Code Generation Initiated", "running", "Staging code into isolated workspace (~/.brownfield-ide/migrations/)")

                gen_req = MigrationGenerateRequest(
                    scope=req.scope,
                    target_path=req.target_path,
                    source_lang=req.source_lang,
                    target_lang=req.target_lang,
                    source_language=req.source_language,
                    target_language=req.target_language,
                    source_version=req.source_version,
                    target_version=req.target_version,
                    strategies=req.strategies or [],
                    max_files=100,
                )

                await migration_agent_service.run_generation(project_path, gen_req)
                gen_status = migration_agent_service.get_status()

                self.global_progress = 60.0
                self.log_step(
                    "Phase 3",
                    "Code Generation Completed",
                    "success",
                    f"Generated {gen_status.summary.files_generated} files under staging '{gen_status.staging_path}'"
                )

                # -------------------------------------------------------------
                # Phase 4: Migration Validation & Review
                # -------------------------------------------------------------
                self.state = "validating"
                self.global_progress = 70.0
                self.log_step("Phase 4", "Validation Pass Initiated", "running", "Running 6 validation passes (Syntax, Deps, Arch, Config, Consistency, Risk)")

                await migration_validation_service.run_validation()
                val_status = migration_validation_service.get_status()
                val_report = val_status.report

                val_score = val_report.validation_score if val_report else 0
                val_risk = val_report.risk_level if val_report else "MANUAL REVIEW"

                self.global_progress = 85.0
                total_issues = (val_report.summary.syntax_errors + val_report.summary.dependency_issues + val_report.summary.architecture_issues + val_report.summary.configuration_issues + val_report.summary.consistency_issues) if val_report else 0
                self.log_step(
                    "Phase 4",
                    "Validation Completed",
                    "success" if val_score >= 80 else "warning",
                    f"Score: {val_score}/100, Risk: {val_risk}, Total Issues: {total_issues}"
                )

                # Auto-approve safe files if requested or if clean
                if req.auto_apply:
                    self.log_step("Phase 4", "Auto-approving Safe Files", "running", "Applying security policy (only safe/warning files approved)")
                    migration_validation_service.approve_all_safe()

                # Check approval state
                approval_output = migration_validation_service.get_approval_output()
                approved_count = len(approval_output.approved_files)

                if approved_count > 0:
                    self.state = "approved"
                    self.log_step("Phase 4", "Approval Workflow Ready", "success", f"{approved_count} files approved and ready for application")

                # -------------------------------------------------------------
                # Phase 5: Apply Migration (if auto_apply and approved files exist)
                # -------------------------------------------------------------
                if req.auto_apply and approved_count > 0:
                    self.state = "applying"
                    self.global_progress = 90.0
                    self.log_step("Phase 5", "Applying Migration Changes", "running", "Creating safety backup before updating source files")

                    apply_report = migration_apply_service.apply_migration(project_path)
                    self.log_step(
                        "Phase 5",
                        "Migration Applied Successfully",
                        "success",
                        f"Applied {len(apply_report.applied_files)} files, backup created at '{apply_report.backup_location}'"
                    )

                self.state = "completed"
                self.global_progress = 100.0
                total_duration = round(time.time() - self._start_time, 2)
                self.log_step(
                    "Platform",
                    "Workflow Completed",
                    "success",
                    f"End-to-end migration lifecycle completed in {total_duration}s"
                )

            except asyncio.CancelledError:
                self.state = "failed"
                self.error_message = "Workflow was cancelled by user."
                self.log_step("Platform", "Workflow Cancelled", "warning", "Execution cancelled by user")
            except Exception as exc:
                self.state = "failed"
                self.error_message = str(exc)
                logger.error(f"Migration Orchestrator workflow failed: {exc}", exc_info=True)
                self.log_step("Platform", "Workflow Failed", "error", f"Error: {exc}")

    def cancel_workflow(self) -> None:
        """Cancel active workflow task safely."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self.state = "failed"
        self.error_message = "Cancelled by user"

    def get_dashboard_summary(self) -> UnifiedDashboardResponse:
        """Build the complete enterprise platform dashboard view."""
        project_path = get_current_project() or str(Path.cwd())
        project_name = Path(project_path).name

        settings_summary = config_manager.get_settings_summary()
        active_llm = get_active_provider()
        
        provider_key = active_llm.key if active_llm else settings_summary.get("current_provider", "ollama")
        model_name = active_llm.model if active_llm else config_manager.get_model(provider_key)
        ollama_installed = config_manager.is_ollama_installed()

        plan = migration_service.active_plan
        source_lang = plan.source_language if plan else "Unknown"
        target_lang = plan.target_language if plan else "java"
        framework = plan.framework if plan else "Unknown"
        arch = plan.architecture if plan else "Unknown"
        scope = plan.scope if plan else "project"
        total_files = plan.total_files_count if plan else 0
        selected_files = plan.included_files_count if plan else 0

        gen_status = migration_agent_service.get_status()
        gen_count = gen_status.summary.files_generated if gen_status and gen_status.summary else 0

        val_status = migration_validation_service.get_status()
        val_report = val_status.report if val_status else None
        val_score = round(val_report.validation_score) if val_report else 0
        val_risk = val_report.risk_level if val_report else "N/A"
        warn_count = val_report.summary.warnings if (val_report and val_report.summary) else 0
        err_count = val_report.summary.failed if (val_report and val_report.summary) else 0

        history = migration_apply_service.get_history()
        applied_count = 0
        rollback_avail = False
        active_mig_id = None

        if history:
            latest = history[0]
            applied_count = latest.files_applied if not latest.rolled_back else 0
            rollback_avail = latest.rollback_available and not latest.rolled_back
            active_mig_id = latest.migration_id

        return UnifiedDashboardResponse(
            project_name=project_name,
            project_path=project_path,
            current_provider=provider_key,
            current_model=model_name,
            ollama_installed=ollama_installed,
            source_language=source_lang,
            target_language=target_lang,
            framework=framework,
            architecture=arch,
            migration_scope=scope,
            workflow_state=self.state,
            global_progress=round(self.global_progress, 1),
            total_files=total_files,
            selected_files=selected_files,
            generated_files=gen_count,
            applied_files=applied_count,
            warnings_count=warn_count,
            errors_count=err_count,
            validation_score=val_score,
            risk_category=val_risk,
            rollback_available=rollback_avail,
            active_migration_id=active_mig_id,
        )

    def get_workflow_status(self) -> WorkflowStatusResponse:
        """Return the current workflow execution status and log stream."""
        return WorkflowStatusResponse(
            workflow_id=self.workflow_id,
            state=self.state,
            global_progress=round(self.global_progress, 1),
            current_phase=self.current_phase,
            current_step=self.current_step,
            step_logs=self.step_logs,
            dashboard=self.get_dashboard_summary(),
            error=self.error_message or None,
        )

    def get_archived_report(self, migration_id: str) -> Optional[ArchivedMigrationReport]:
        """Load and build a complete historical report for reopening past runs."""
        record = migration_apply_service.get_record(migration_id)
        if not record:
            return None

        project_path = get_current_project() or str(Path.cwd())
        project_name = Path(project_path).name

        plan_markdown = migration_service.get_report_markdown() if migration_service.active_plan else ""
        val_status = migration_validation_service.get_status()
        val_markdown = val_status.report.report_markdown if val_status and val_status.report else ""

        return ArchivedMigrationReport(
            migration_id=record.migration_id,
            created_at=record.timestamp,
            project_name=project_name,
            provider=record.provider,
            model=record.model,
            source_language=record.source_language,
            target_language=record.target_language,
            scope=record.scope,
            validation_score=record.validation_score,
            duration_s=round(record.duration_ms / 1000.0, 2),
            summary=record.summary,
            plan_markdown=plan_markdown,
            validation_markdown=val_markdown,
            apply_markdown=record.report_markdown,
        )


# Singleton instance
migration_orchestrator = MigrationOrchestrator()
