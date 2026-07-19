# Agentic Brownfield Development Environment & AI Code Migration Agent
## Complete REST API Documentation

This document provides a complete reference for all 56 REST endpoints and WebSocket interfaces provided by the backend FastAPI service.

---

## Table of Contents
1. [System & Health Endpoints](#1-system--health-endpoints)
2. [Filesystem & Workspace Endpoints](#2-filesystem--workspace-endpoints)
3. [Integrated Terminal Endpoints](#3-integrated-terminal-endpoints)
4. [Project Analysis & Understanding Endpoints](#4-project-analysis--understanding-endpoints)
5. [Intelligent Code Search Endpoints](#5-intelligent-code-search-endpoints)
6. [Architecture Impact Analysis Endpoints](#6-architecture-impact-analysis-endpoints)
7. [Development Agent Endpoints](#7-development-agent-endpoints)
8. [Validation & Approval Endpoints](#8-validation--approval-endpoints)
9. [Source Code Update & History Endpoints](#9-source-code-update--history-endpoints)
10. [AI Code Migration Agent Endpoints (Phases 2–6)](#10-ai-code-migration-agent-endpoints-phases-26)

---

## 1. System & Health Endpoints

### `GET /api/health`
* **Purpose**: System health check.
* **Request**: None.
* **Response**: `{"status": "ok", "version": "1.0.0"}`
* **Module**: `backend/main.py`

---

## 2. Filesystem & Workspace Endpoints

### `POST /api/workspace/open`
* **Purpose**: Open a local workspace directory and set it as the active project.
* **Request Body**: `{"path": "string"}`
* **Response**: `{"success": true, "project_path": "string", "name": "string"}`
* **Module**: `backend/routers/workspace.py`

### `GET /api/workspace/current`
* **Purpose**: Get metadata for the currently active workspace.
* **Request Params**: None.
* **Response**: `{"active": true, "path": "string", "name": "string"}`
* **Module**: `backend/routers/workspace.py`

### `GET /api/workspace/recent`
* **Purpose**: Retrieve recent workspace path history.
* **Request Params**: None.
* **Response**: `{"recent": ["string"]}`
* **Module**: `backend/routers/workspace.py`

### `GET /api/fs/tree`
* **Purpose**: Retrieve directory tree hierarchy with lazy loading.
* **Request Params**: `path` (optional, string), `depth` (optional, default=1).
* **Response**: `TreeNode` object containing `name`, `path`, `is_dir`, `size`, `children`.
* **Module**: `backend/routers/filesystem.py`

### `GET /api/fs/file`
* **Purpose**: Read file contents for Monaco Editor.
* **Request Params**: `path` (required, relative path).
* **Response**: `{"path": "string", "content": "string", "encoding": "utf-8", "size": 1234}`
* **Module**: `backend/routers/filesystem.py`

### `PUT /api/fs/file`
* **Purpose**: Write or update file content on disk.
* **Request Body**: `{"path": "string", "content": "string"}`
* **Response**: `{"success": true, "path": "string", "bytes_written": 1234}`
* **Module**: `backend/routers/filesystem.py`

### `POST /api/fs/file`
* **Purpose**: Create a new file or directory.
* **Request Body**: `{"path": "string", "is_dir": false}`
* **Response**: `{"success": true, "path": "string"}`
* **Module**: `backend/routers/filesystem.py`

### `DELETE /api/fs/file`
* **Purpose**: Delete a file or directory.
* **Request Params**: `path` (required, relative path).
* **Response**: `{"success": true, "message": "Deleted successfully."}`
* **Module**: `backend/routers/filesystem.py`

### `POST /api/fs/zip/open`
* **Purpose**: Ingest and extract a uploaded `.zip` project archive.
* **Request**: Multipart form data with ZIP file payload.
* **Response**: `{"success": true, "project_path": "string", "files_extracted": 42}`
* **Module**: `backend/routers/filesystem.py`

---

## 3. Integrated Terminal Endpoints

### `POST /api/terminal/create`
* **Purpose**: Create a new PTY interactive terminal session.
* **Request Body**: `{"cwd": "string" (optional), "cols": 80, "rows": 24}`
* **Response**: `{"session_id": "uuid-string", "cwd": "string"}`
* **Module**: `backend/routers/terminal.py`

### `GET /api/terminal/sessions`
* **Purpose**: List all active terminal sessions.
* **Request Params**: None.
* **Response**: `[{"session_id": "string", "cwd": "string", "created_at": "string"}]`
* **Module**: `backend/routers/terminal.py`

### `DELETE /api/terminal/{session_id}`
* **Purpose**: Terminate and clean up a terminal session.
* **Request Params**: `session_id` (path parameter).
* **Response**: `{"success": true, "message": "Session terminated."}`
* **Module**: `backend/routers/terminal.py`

### `WebSocket /ws/terminal/{session_id}`
* **Purpose**: Bi-directional real-time terminal input/output stream.
* **Inbound JSON**: `{"type": "input", "data": "ls\r"}` or `{"type": "resize", "cols": 100, "rows": 30}`
* **Outbound JSON**: `{"type": "output", "data": "text output"}`
* **Module**: `backend/routers/terminal.py`

---

## 4. Project Analysis & Understanding Endpoints

### `POST /api/analysis/analyze`
* **Purpose**: Trigger asynchronous background static analysis of the active project.
* **Request Params**: None.
* **Response**: `{"success": true, "message": "Analysis initiated."}`
* **Module**: `backend/routers/analysis.py`

### `GET /api/analysis/status`
* **Purpose**: Query analysis scanner progress, log steps, and summary counters.
* **Request Params**: None.
* **Response**: `MigrationStatusResponse` containing `status`, `progress`, `step_logs`, `summary`.
* **Module**: `backend/routers/analysis.py`

### `POST /api/analysis/explain`
* **Purpose**: Generate AI explanation for a code target (project/file/class/function).
* **Request Body**: `{"scope": "string", "target": "string", "active_file": "string", "cursor_line": 10}`
* **Response**: `{"success": true, "explanation": "string"}`
* **Module**: `backend/routers/analysis.py`

---

## 5. Intelligent Code Search Endpoints

### `GET /api/fs/search`
* **Purpose**: Keyword and symbol search across codebase.
* **Request Params**: `q` (search query string).
* **Response**: List of search hit items `[{"file": "string", "line": 10, "content": "string"}]`
* **Module**: `backend/routers/filesystem.py`

### `POST /api/search/query`
* **Purpose**: Advanced semantic and structural symbol query.
* **Request Body**: `{"query": "string", "symbol_type": "class|function|api"}`
* **Response**: `{"results": [...], "total": 15}`
* **Module**: `backend/routers/search.py`

---

## 6. Architecture Impact Analysis Endpoints

### `GET /api/impact/graph`
* **Purpose**: Fetch full node-edge dependency graph data for visual rendering.
* **Request Params**: None.
* **Response**: `{"nodes": [{"id": "string", "label": "string", "group": "file|class|func|api"}], "edges": [{"from": "id", "to": "id", "label": "imports"}]}`
* **Module**: `backend/routers/impact.py`

### `GET /api/impact/analyze`
* **Purpose**: Trace direct and indirect dependencies for a change target.
* **Request Params**: `type` (`file|class|func`), `target` (path or symbol name).
* **Response**: `{"target": "string", "dependents": [...], "dependencies": [...]}`
* **Module**: `backend/routers/impact.py`

### `GET /api/impact/risk`
* **Purpose**: Compute change risk indicators and score metrics.
* **Request Params**: `target` (path or symbol name).
* **Response**: `{"target": "string", "risk": {"level": "Low|Medium|High", "explanation": "string", "metrics": {...}}}`
* **Module**: `backend/routers/impact.py`

---

## 7. Development Agent Endpoints

### `POST /api/agent/develop`
* **Purpose**: Process natural-language developer request and generate proposed change bundle.
* **Request Body**: `{"request": "string"}`
* **Response**: `{"plan_id": "string", "intent": "feature|bug_fix|refactor", "patches": [...], "understanding": {...}}`
* **Module**: `backend/routers/agent.py`

### `GET /api/agent/result/{plan_id}`
* **Purpose**: Re-fetch a cached proposed change bundle by `plan_id`.
* **Request Params**: `plan_id` (path parameter).
* **Response**: Proposed change set object.
* **Module**: `backend/routers/agent.py`

### `GET /api/agent/providers`
* **Purpose**: List available AI providers and active status.
* **Request Params**: None.
* **Response**: `{"providers": [{"key": "ollama", "name": "Ollama", "active": true}]}`
* **Module**: `backend/routers/agent.py`

### `GET /api/agent/settings`
* **Purpose**: Get central AI settings summary.
* **Request Params**: None.
* **Response**: Settings dictionary with active provider and credentials status.
* **Module**: `backend/routers/agent.py`

### `POST /api/agent/settings`
* **Purpose**: Update central AI settings (hot-swap provider or API keys).
* **Request Body**: `{"current_provider": "gemini", "providers": {...}}`
* **Response**: `{"success": true, "settings": {...}}`
* **Module**: `backend/routers/agent.py`

---

## 8. Validation & Approval Endpoints

### `POST /api/validation/validate`
* **Purpose**: Run 6-pass safety validation pipeline on a proposed agent plan.
* **Request Body**: `{"plan_id": "string", "force": false}`
* **Response**: `ValidationReport` with `risk_score`, `status`, `syntax`, `static`, `next_phase`.
* **Module**: `backend/routers/validation.py`

### `GET /api/validation/report/{plan_id}`
* **Purpose**: Fetch a cached validation report by plan_id.
* **Request Params**: `plan_id` (path parameter).
* **Response**: `ValidationReport` object.
* **Module**: `backend/routers/validation.py`

### `POST /api/validation/approve`
* **Purpose**: Record user approval decision.
* **Request Body**: `{"plan_id": "string"}`
* **Response**: `{"state": "approved", "at": "timestamp"}`
* **Module**: `backend/routers/validation.py`

### `POST /api/validation/reject`
* **Purpose**: Record user rejection decision.
* **Request Body**: `{"plan_id": "string"}`
* **Response**: `{"state": "rejected", "at": "timestamp"}`
* **Module**: `backend/routers/validation.py`

### `GET /api/validation/decision/{plan_id}`
* **Purpose**: Fetch current approval decision state.
* **Request Params**: `plan_id` (path parameter).
* **Response**: `{"state": "approved|rejected|pending", "at": "timestamp"}`
* **Module**: `backend/routers/validation.py`

---

## 9. Source Code Update & History Endpoints

### `POST /api/source/apply`
* **Purpose**: Apply approved agent change set to disk with automatic backup.
* **Request Body**: `{"plan_id": "string", "commit": false}`
* **Response**: `{"status": "SUCCESS", "operation_id": "string", "files_updated": [...]}`
* **Module**: `backend/routers/source.py`

### `POST /api/source/undo`
* **Purpose**: Undo the last applied change set.
* **Request Params**: None.
* **Response**: `{"status": "UNDONE", "restored_files": [...]}`
* **Module**: `backend/routers/source.py`

### `POST /api/source/rollback`
* **Purpose**: Roll back a specific change operation by operation_id.
* **Request Body**: `{"operation_id": "string"}`
* **Response**: `{"status": "UNDONE", "operation_id": "string"}`
* **Module**: `backend/routers/source.py`

### `GET /api/source/history`
* **Purpose**: List persistent change history.
* **Request Params**: None.
* **Response**: `{"history": [...]}`
* **Module**: `backend/routers/source.py`

### `GET /api/source/backups`
* **Purpose**: List available disk backup snapshots.
* **Request Params**: None.
* **Response**: `{"backups": [...]}`
* **Module**: `backend/routers/source.py`

---

## 10. AI Code Migration Agent Endpoints (Phases 2–6)

### `POST /api/migration/analyze`
* **Purpose**: Trigger Phase 2 Migration Analysis scan for scope, strategy, and optional language version.
* **Request Body**: `{"scope": "file|folder|frontend|backend|database|project", "target_path": "string", "source_lang": "py", "target_lang": "java", "source_version": "3.8", "target_version": "3.12", "strategies": ["rewrite"]}`
* **Response**: `{"success": true, "message": "Migration analysis initiated."}`
* **Module**: `backend/routers/migration.py`

### `GET /api/migration/status`
* **Purpose**: Get scanner progress and Migration Plan.
* **Request Params**: None.
* **Response**: `MigrationStatusResponse` object.
* **Module**: `backend/routers/migration.py`

### `GET /api/migration/plan`
* **Purpose**: Fetch active Migration Plan object.
* **Request Params**: None.
* **Response**: `{"success": true, "plan": MigrationPlan}`
* **Module**: `backend/routers/migration.py`

### `POST /api/migration/generate`
* **Purpose**: Trigger Phase 3 AI Code Migration generation to isolated staging workspace.
* **Request Body**: `{"source_language": "python", "target_language": "java", "source_version": "3.8", "target_version": "3.12"}`
* **Response**: `{"success": true, "message": "AI migration generation initiated."}`
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/generate/status`
* **Purpose**: Get generation progress, status, and staged file list.
* **Request Params**: None.
* **Response**: `MigrationGenerationStatus` object.
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/download/project`
* **Purpose**: Download entire generated migrated project as a ZIP archive.
* **Request Params**: None.
* **Response**: Binary stream (`application/zip`) with `Content-Disposition` header.
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/download/folder`
* **Purpose**: Download a specific migrated folder as a ZIP archive.
* **Request Params**: `path` (relative folder path in staging workspace).
* **Response**: Binary stream (`application/zip`) with `Content-Disposition` header.
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/download/file`
* **Purpose**: Download a single generated file as a ZIP archive.
* **Request Params**: `path` (relative file path in staging workspace).
* **Response**: Binary stream (`application/zip`) with `Content-Disposition` header.
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/download/info`
* **Purpose**: Get ZIP download size and file count metadata before downloading.
* **Request Params**: `type` (`file|folder|project`), `path` (optional string).
* **Response**: `{"success": true, "file_count": 5, "zip_size_bytes": 1024, "formatted_zip_size": "1.0 KB", "staging_path": "string"}`
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/generate/file`
* **Purpose**: Fetch single generated file content and diff payload.
* **Request Params**: `path` (relative to staging root).
* **Response**: `{"success": true, "file": GeneratedFile}`
* **Module**: `backend/routers/migration_agent.py`

### `GET /api/migration/generate/handoff`
* **Purpose**: Fetch Phase 4/5/6 hand-off envelope object.
* **Request Params**: None.
* **Response**: `{"success": true, "handoff": HandoffEnvelope}`
* **Module**: `backend/routers/migration_agent.py`

### `POST /api/migration/generate/reset`
* **Purpose**: Reset generation state in memory.
* **Request Params**: None.
* **Response**: `{"success": true, "message": "Migration generation state reset."}`
* **Module**: `backend/routers/migration_agent.py`

### `POST /api/migration/validate`
* **Purpose**: Run Phase 4 6-pass validation engine on staged files.
* **Request Params**: None.
* **Response**: `{"success": true, "status": MigrationValidationStatus}`
* **Module**: `backend/routers/migration_validation.py`

### `GET /api/migration/validation/status`
* **Purpose**: Query validation status and safety report.
* **Request Params**: None.
* **Response**: `{"success": true, "status": MigrationValidationStatus}`
* **Module**: `backend/routers/migration_validation.py`

### `POST /api/migration/approval/decision`
* **Purpose**: Set file-level or bulk approval decision.
* **Request Body**: `{"action": "approve|reject|approve_all_safe", "generated_path": "string"}`
* **Response**: `{"success": true, "result": {...}}`
* **Module**: `backend/routers/migration_validation.py`

### `GET /api/migration/changes`
* **Purpose**: Preview change set items to be written in Phase 5.
* **Request Params**: None.
* **Response**: `ChangeSet` object.
* **Module**: `backend/routers/migration_apply.py`

### `POST /api/migration/apply`
* **Purpose**: Apply approved migration files to disk with pre-apply backup.
* **Request Body**: `{"applied_by": "user"}`
* **Response**: `FinalReport` object.
* **Module**: `backend/routers/migration_apply.py`

### `POST /api/migration/rollback`
* **Purpose**: Revert applied migration byte-for-byte using backup snapshot.
* **Request Body**: `{"migration_id": "string", "file": "string" (optional)}`
* **Response**: `{"success": true, "message": "Rollback completed."}`
* **Module**: `backend/routers/migration_apply.py`

### `GET /api/migration/history`
* **Purpose**: List persistent migration application history.
* **Request Params**: None.
* **Response**: `{"success": true, "history": [...]}`
* **Module**: `backend/routers/migration_apply.py`

### `POST /api/migration/workflow/start`
* **Purpose**: Start Phase 6 multi-step migration workflow orchestrator.
* **Request Body**: `{"target_language": "java", "scope": "file"}`
* **Response**: `{"success": true, "workflow_id": "string"}`
* **Module**: `backend/routers/migration_orchestrator.py`

### `POST /api/migration/workflow/cancel`
* **Purpose**: Cancel active migration workflow orchestrator task.
* **Request Params**: None.
* **Response**: `{"success": true, "message": "Migration workflow cancelled."}`
* **Module**: `backend/routers/migration_orchestrator.py`

### `GET /api/migration/workflow/dashboard`
* **Purpose**: Get unified orchestrator state, summary counters, and provider status.
* **Request Params**: None.
* **Response**: Unified dashboard summary JSON object.
* **Module**: `backend/routers/migration_orchestrator.py`
