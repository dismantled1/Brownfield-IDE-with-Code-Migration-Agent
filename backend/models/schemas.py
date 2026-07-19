"""
Pydantic schemas for the Brownfield IDE API.
"""

from __future__ import annotations
from typing import Optional, List, Literal, Any, Dict
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# File System Schemas
# ---------------------------------------------------------------------------

class FileNode(BaseModel):
    """Represents a file or folder in the project tree."""
    name: str
    path: str  # Relative to project root, forward-slash separated
    type: Literal["file", "folder"]
    extension: Optional[str] = None  # e.g. "js", "py", "json"
    size: Optional[int] = None       # Bytes (files only)
    modified: Optional[float] = None  # Unix timestamp
    # None = folder not yet expanded (lazy load)
    # []   = folder is empty
    # [..] = folder children (loaded)
    children: Optional[List[FileNode]] = None

    model_config = {"populate_by_name": True}


FileNode.model_rebuild()  # Required for self-referential model


class FileContent(BaseModel):
    """File content returned from the API."""
    path: str
    content: str
    size: int
    encoding: str = "utf-8"
    language: Optional[str] = None  # Monaco language ID


class WriteFileRequest(BaseModel):
    """Request body for writing a file."""
    path: str = Field(..., description="Relative path from project root")
    content: str = Field(..., description="File content to write")


class CreateFileRequest(BaseModel):
    """Request body for creating a new file."""
    path: str = Field(..., description="Relative path from project root")


class CreateFolderRequest(BaseModel):
    """Request body for creating a new folder."""
    path: str = Field(..., description="Relative path from project root")


class DeleteRequest(BaseModel):
    """Request body for deleting a file or folder."""
    path: str = Field(..., description="Relative path from project root")


class RenameRequest(BaseModel):
    """Request body for renaming a file or folder."""
    path: str = Field(..., description="Current relative path from project root")
    new_name: str = Field(..., description="New name (not full path, just the filename/dirname)")


class SearchResult(BaseModel):
    """A search result entry."""
    nodes: List[FileNode]
    total: int
    query: str


# ---------------------------------------------------------------------------
# Workspace Schemas
# ---------------------------------------------------------------------------

class RecentProject(BaseModel):
    """A recently opened project."""
    path: str
    name: str
    opened_at: str  # ISO 8601 timestamp


class WorkspaceState(BaseModel):
    """Persisted workspace state."""
    current_project: Optional[str] = None
    recent_projects: List[RecentProject] = []


class OpenProjectRequest(BaseModel):
    """Request to open a project by absolute path."""
    path: str = Field(..., description="Absolute path to the project folder")


class OpenProjectResponse(BaseModel):
    """Response after opening a project."""
    project_name: str
    project_path: str
    tree: FileNode


# ---------------------------------------------------------------------------
# Terminal Schemas
# ---------------------------------------------------------------------------

class TerminalSessionInfo(BaseModel):
    """Information about a terminal session."""
    session_id: str
    cwd: str
    alive: bool
    created_at: str


class CreateTerminalRequest(BaseModel):
    """Request to create a terminal session."""
    cwd: Optional[str] = None
    cols: int = 80
    rows: int = 24


class CreateTerminalResponse(BaseModel):
    """Response after creating a terminal session."""
    session_id: str
    cwd: str


# ---------------------------------------------------------------------------
# Generic Response
# ---------------------------------------------------------------------------

class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Generic error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Migration Schemas (Phase 2 Code Migration Agent)
# ---------------------------------------------------------------------------

class MigrationAnalysisRequest(BaseModel):
    """Request payload for starting migration analysis."""
    scope: Literal["file", "folder", "frontend", "backend", "database", "project"] = "project"
    target_path: Optional[str] = Field(default=None, description="Relative path if scope is file or folder")
    source_lang: Optional[str] = Field(default="auto", description="Source language selection")
    target_lang: Optional[str] = Field(default="java", description="Target language selection")
    source_language: Optional[str] = Field(default=None, description="Source language selection alias")
    target_language: Optional[str] = Field(default=None, description="Target language selection alias")
    source_version: Optional[str] = Field(default=None, description="Optional source language version")
    target_version: Optional[str] = Field(default=None, description="Optional target language version")
    strategies: Optional[List[str]] = Field(default_factory=list, description="Selected migration strategies")


class MigrationComponentBreakdown(BaseModel):
    """Fine-grained classification of project components."""
    controllers: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    repositories: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    dtos: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    interfaces: List[str] = Field(default_factory=list)
    utilities: List[str] = Field(default_factory=list)
    exceptions: List[str] = Field(default_factory=list)
    test_files: List[str] = Field(default_factory=list)


class MigrationAssetCategory(BaseModel):
    """Categorization of key project assets."""
    config_files: List[str] = Field(default_factory=list)
    environment_files: List[str] = Field(default_factory=list)
    auth_security_modules: List[str] = Field(default_factory=list)
    middleware: List[str] = Field(default_factory=list)
    api_routes: List[str] = Field(default_factory=list)
    static_resources: List[str] = Field(default_factory=list)
    build_scripts: List[str] = Field(default_factory=list)
    deployment_files: List[str] = Field(default_factory=list)


class MigrationPlan(BaseModel):
    """Migration Plan model generated by Migration Analysis Engine."""
    project_path: str
    source_language: str = "Unknown"
    secondary_languages: Dict[str, float] = Field(default_factory=dict)
    target_language: str = "Java"
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    project_type: str = "Web Application"
    framework: str = "Unknown"
    architecture: str = "Layered Architecture"
    scope: str = "project"
    target_path: Optional[str] = None
    files_included: List[str] = Field(default_factory=list)
    files_excluded: List[str] = Field(default_factory=list)
    total_files_count: int = 0
    included_files_count: int = 0
    excluded_files_count: int = 0
    components: MigrationComponentBreakdown = Field(default_factory=MigrationComponentBreakdown)
    assets: MigrationAssetCategory = Field(default_factory=MigrationAssetCategory)
    internal_dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    external_dependencies: List[str] = Field(default_factory=list)
    database_connections: List[str] = Field(default_factory=list)
    entry_points: List[str] = Field(default_factory=list)
    estimated_complexity: str = "Medium"
    estimated_size_loc: int = 0
    estimated_size_bytes: int = 0
    report_markdown: str = ""


class MigrationStatusResponse(BaseModel):
    """Response payload for migration analysis status & progress."""
    status: str = "idle"
    progress: float = 0.0
    current_step: str = ""
    current_file: str = ""
    step_logs: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    plan: Optional[MigrationPlan] = None


# ---------------------------------------------------------------------------
# Migration Agent Schemas (Phase 3 — AI Migration Agent / Code Generation)
# ---------------------------------------------------------------------------

class MigrationGenerateRequest(BaseModel):
    """Request payload to start AI code generation from the active Migration Plan.

    Scope / target selection mirrors the analysis request. The engine REUSES the
    Phase 2 Migration Plan (it does NOT rescan the project) and generates code
    into an isolated staging workspace — the original project is never modified.
    """
    scope: Literal["file", "folder", "frontend", "backend", "database", "project"] = "project"
    target_path: Optional[str] = Field(default=None, description="Relative path if scope is file or folder")
    source_lang: Optional[str] = Field(default="auto", description="Source language selection")
    target_lang: Optional[str] = Field(default="java", description="Target language selection")
    source_language: Optional[str] = Field(default=None, description="Source language selection alias")
    target_language: Optional[str] = Field(default=None, description="Target language selection alias")
    source_version: Optional[str] = Field(default=None, description="Optional source language version")
    target_version: Optional[str] = Field(default=None, description="Optional target language version")
    strategies: Optional[List[str]] = Field(default_factory=list, description="Selected migration strategies")
    max_files: int = Field(default=40, ge=1, le=500, description="Max number of files to translate per run")


class GeneratedFileDiffRow(BaseModel):
    """A single aligned row for the split diff view."""
    type: Literal["equal", "add", "remove", "modify"] = "equal"
    left_num: Optional[int] = None
    right_num: Optional[int] = None
    left: str = ""
    right: str = ""


class GeneratedFileMeta(BaseModel):
    """Lightweight generated-file descriptor (used in status / explorer listings)."""
    original_path: Optional[str] = None
    generated_path: str
    component_type: str = "other"
    language: str = "plaintext"
    status: Literal["new", "modified", "skipped", "failed"] = "new"
    provider: str = "offline"
    additions: int = 0
    removals: int = 0
    error: Optional[str] = None
    reason: Optional[str] = None


class GeneratedFile(GeneratedFileMeta):
    """Full generated-file payload including content + diff (detail endpoint)."""
    original_content: str = ""
    generated_content: str = ""
    diff: str = ""
    diff_rows: List[GeneratedFileDiffRow] = Field(default_factory=list)


class MigrationGenerationSummary(BaseModel):
    """Aggregate counters for a generation run."""
    files_selected: int = 0
    files_generated: int = 0
    new_files: int = 0
    modified_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    warnings: int = 0
    errors: int = 0
    additions: int = 0
    removals: int = 0


class MigrationGenerationStatus(BaseModel):
    """Response payload for AI migration generation status & progress."""
    status: str = "idle"  # idle, generating, completed, failed
    progress: float = 0.0
    current_step: str = ""
    current_file: str = ""
    step_logs: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    session_id: Optional[str] = None
    staging_path: Optional[str] = None
    provider: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    scope: Optional[str] = None
    summary: MigrationGenerationSummary = Field(default_factory=MigrationGenerationSummary)
    files: List[GeneratedFileMeta] = Field(default_factory=list)
    handoff: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Migration Validation & Approval Schemas (Phase 4)
# ---------------------------------------------------------------------------

class FileValidationIssue(BaseModel):
    """A single issue found while validating one generated file."""
    category: Literal["syntax", "dependency", "architecture", "configuration", "consistency"]
    severity: Literal["error", "warning", "info"] = "warning"
    message: str
    line: Optional[int] = None
    detail: Optional[str] = None


class FileValidationResult(BaseModel):
    """Per-file validation outcome + approval state."""
    generated_path: str
    original_path: Optional[str] = None
    component_type: str = "other"
    language: str = "plaintext"
    generation_status: str = "new"          # status carried over from Phase 3
    validation_status: Literal["passed", "warning", "failed", "manual_review"] = "passed"
    risk: Literal["safe", "warning", "high_risk", "manual_review"] = "safe"
    score: float = 100.0
    auto_approvable: bool = True
    approval: Literal["pending", "approved", "rejected"] = "pending"
    issues: List[FileValidationIssue] = Field(default_factory=list)
    missing_dependencies: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    """Aggregate validation counters."""
    total_files: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    manual_review: int = 0
    safe_files: int = 0
    high_risk: int = 0
    syntax_errors: int = 0
    dependency_issues: int = 0
    architecture_issues: int = 0
    configuration_issues: int = 0
    consistency_issues: int = 0


class ValidationReport(BaseModel):
    """Full validation report produced by the validation engine."""
    session_id: Optional[str] = None
    staging_path: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    scope: Optional[str] = None
    generated_at: str = ""
    validation_score: float = 0.0
    success_percentage: float = 0.0
    risk_level: str = "Low"
    summary: ValidationSummary = Field(default_factory=ValidationSummary)
    files: List[FileValidationResult] = Field(default_factory=list)
    missing_dependencies: List[str] = Field(default_factory=list)
    syntax_errors: List[Dict[str, Any]] = Field(default_factory=list)
    architecture_issues: List[Dict[str, Any]] = Field(default_factory=list)
    configuration_issues: List[Dict[str, Any]] = Field(default_factory=list)
    consistency_issues: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    report_markdown: str = ""


class ValidationStatusResponse(BaseModel):
    """Validation progress + report payload."""
    status: str = "idle"  # idle, validating, completed, failed
    progress: float = 0.0
    current_step: str = ""
    step_logs: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    report: Optional[ValidationReport] = None


class ApprovalActionRequest(BaseModel):
    """Approve/reject a single file by its generated path."""
    path: str = Field(..., description="Generated file path (relative to staging root)")


class ApprovalOutput(BaseModel):
    """Approval decisions consumed by Phase 5 (Apply Migration)."""
    session_id: Optional[str] = None
    staging_path: Optional[str] = None
    target_language: Optional[str] = None
    generated_at: str = ""
    approved_files: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_files: List[Dict[str, Any]] = Field(default_factory=list)
    pending_review_files: List[Dict[str, Any]] = Field(default_factory=list)
    validation_metadata: Dict[str, Any] = Field(default_factory=dict)
    ready_for_apply: bool = False


# ---------------------------------------------------------------------------
# Migration Application Schemas (Phase 5 — Apply / Rollback / History)
# ---------------------------------------------------------------------------

class ChangeSetItem(BaseModel):
    """One planned change in the apply change set."""
    generated_path: str
    original_path: Optional[str] = None
    target_path: str                      # where it will be written (relative to project root)
    mode: Literal["create", "replace", "modify", "rename", "delete", "merge"] = "create"
    component_type: str = "other"
    language: str = "plaintext"
    exists: bool = False                  # target already present in the project
    additions: int = 0
    removals: int = 0


class ChangeSet(BaseModel):
    """Preview of everything that will change if the migration is applied."""
    ready: bool = False
    project_root: Optional[str] = None
    target_language: Optional[str] = None
    to_create: List[ChangeSetItem] = Field(default_factory=list)
    to_replace: List[ChangeSetItem] = Field(default_factory=list)
    to_modify: List[ChangeSetItem] = Field(default_factory=list)
    to_delete: List[ChangeSetItem] = Field(default_factory=list)
    to_rename: List[ChangeSetItem] = Field(default_factory=list)
    skipped: List[Dict[str, Any]] = Field(default_factory=list)
    total_approved: int = 0
    message: Optional[str] = None


class ApplyRequest(BaseModel):
    """Request to apply the approved migration."""
    applied_by: Optional[str] = Field(default=None, description="Who applied the migration")


class MigrationRecord(BaseModel):
    """A single migration-application record for history + rollback."""
    migration_id: str
    timestamp: str
    project_root: str
    target_language: Optional[str] = None
    applied_by: Optional[str] = None
    files_applied: int = 0
    files_created: int = 0
    files_replaced: int = 0
    files_deleted: int = 0
    files_skipped: int = 0
    backup_location: str = ""
    duration_ms: float = 0.0
    validation_score: Optional[float] = None
    rollback_available: bool = True
    rolled_back: bool = False
    rolled_back_at: Optional[str] = None
    changes: List[Dict[str, Any]] = Field(default_factory=list)


class FinalReport(BaseModel):
    """Final application report (also drives the success screen)."""
    success: bool = True
    migration_id: str
    project_root: str
    target_language: Optional[str] = None
    applied_files: List[str] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    new_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    backup_location: str = ""
    rollback_status: str = "available"
    duration_ms: float = 0.0
    summary: Dict[str, Any] = Field(default_factory=dict)
    report_markdown: str = ""


class RollbackRequest(BaseModel):
    """Rollback an entire migration, or a single file within it."""
    migration_id: str = Field(..., description="Migration ID to roll back")
    file: Optional[str] = Field(default=None, description="If set, restore only this target path")


# ---------------------------------------------------------------------------
# Migration Orchestrator Schemas (Phase 6 — Final Integration & Workflow)
# ---------------------------------------------------------------------------

class WorkflowStartRequest(BaseModel):
    """Request payload to initiate or resume an orchestrated migration workflow."""
    scope: Literal["file", "folder", "frontend", "backend", "database", "project"] = "project"
    target_path: Optional[str] = Field(default=None, description="Relative path if scope is file or folder")
    source_lang: Optional[str] = Field(default="auto", description="Source language selection")
    target_lang: Optional[str] = Field(default="java", description="Target language selection")
    strategies: Optional[List[str]] = Field(default_factory=list, description="Migration strategy flags")
    auto_apply: bool = Field(default=False, description="If true, auto-applies safe approved files upon validation")


class WorkflowStepLog(BaseModel):
    """Timestamped log entry for the Live Execution Console."""
    timestamp: str
    phase: str
    step: str
    duration_s: float = 0.0
    status: Literal["info", "running", "success", "warning", "error"] = "info"
    message: str = ""
    details: Optional[Dict[str, Any]] = None


class UnifiedDashboardResponse(BaseModel):
    """Complete enterprise platform state summary for the Unified Dashboard."""
    project_name: str = ""
    project_path: str = ""
    current_provider: str = "ollama"
    current_model: str = ""
    ollama_installed: bool = False
    source_language: str = "Unknown"
    target_language: str = "java"
    framework: str = "Unknown"
    architecture: str = "Unknown"
    migration_scope: str = "project"
    workflow_state: str = "idle"
    global_progress: float = 0.0
    total_files: int = 0
    selected_files: int = 0
    generated_files: int = 0
    applied_files: int = 0
    warnings_count: int = 0
    errors_count: int = 0
    validation_score: int = 0
    risk_category: str = "N/A"
    rollback_available: bool = False
    active_migration_id: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    """Response payload for current orchestrated workflow state."""
    workflow_id: str
    state: str = "idle"  # idle, analyzing, generating, validating, approved, applying, completed, failed, rolled_back
    global_progress: float = 0.0
    current_phase: str = ""
    current_step: str = ""
    step_logs: List[WorkflowStepLog] = Field(default_factory=list)
    dashboard: Optional[UnifiedDashboardResponse] = None
    error: Optional[str] = None


class ArchivedMigrationReport(BaseModel):
    """Complete historical report payload for reopening historical runs."""
    migration_id: str
    created_at: str
    project_name: str
    provider: str
    model: str
    source_language: str
    target_language: str
    scope: str
    validation_score: int
    duration_s: float
    summary: Dict[str, Any] = Field(default_factory=dict)
    plan_markdown: str = ""
    validation_markdown: str = ""
    apply_markdown: str = ""


MigrationPlan.model_rebuild()
MigrationStatusResponse.model_rebuild()
GeneratedFile.model_rebuild()
MigrationGenerationStatus.model_rebuild()
FileValidationResult.model_rebuild()
ValidationReport.model_rebuild()
ValidationStatusResponse.model_rebuild()
ChangeSet.model_rebuild()
FinalReport.model_rebuild()
MigrationRecord.model_rebuild()
WorkflowStatusResponse.model_rebuild()
UnifiedDashboardResponse.model_rebuild()
ArchivedMigrationReport.model_rebuild()



