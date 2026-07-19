# Agentic Brownfield Development Environment & AI Code Migration Agent
## Complete System Overview & Architecture Documentation

---

## 1. Problem Statement

Modern enterprise software systems frequently accumulate decades of technical debt, legacy architectures, obsolete frameworks, and undocumented dependencies. Maintaining and modernizing these "Brownfield" codebases poses critical engineering challenges:

1. **Context Fragmentation**: Understanding legacy code requires traversing complex, multi-layered dependencies across controllers, services, repositories, models, DTOs, and configuration files. Developers spend up to 70% of their time reading and understanding code rather than writing new features.
2. **High Change Risk**: Modifying legacy components without clear dependency tracing often causes regression bugs in distant, unexpected parts of the application.
3. **Migration Friction & Lock-in**: Porting legacy applications across programming languages, frameworks, or database layers (e.g., Python to Java, C# to Java, JavaScript to TypeScript) is notoriously manual, error-prone, and slow. Existing automated migration tools are often locked to a single proprietary LLM provider or lack transactional rollback mechanisms.
4. **Destructive Automated Tools**: AI agents that edit source files directly on disk can corrupt projects if generation fails or fails validation.

---

## 2. Objectives

The **Agentic Brownfield Development Environment** with **AI Code Migration Agent** addresses these challenges through a dual-mode platform:

* **Brownfield IDE**: An intelligent development environment built for existing codebases. It provides instant project understanding, static structure analysis, semantic and structural search, architecture impact analysis, an AI development agent (for feature additions, bug fixes, and refactoring), safety validation, and transactional source updates with undo capabilities.
* **AI Code Migration Agent**: A language-agnostic code transformation pipeline that converts multi-layer legacy software across target languages and architectures. It operates via an isolated staging workspace, multi-pass safety validation engine, provider-agnostic LLM abstraction layer, and byte-for-byte snapshot rollback.

---

## 3. Core System Architecture

The project follows a decoupled, multi-layered architecture:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND LAYER (Vanilla JS + HTML5 + CSS3)            │
│  ┌─────────────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Brownfield IDE UI       │  │ Monaco Editor    │  │ Integrated        │  │
│  │ (Tree, Tabs, Panels)    │  │ (Syntax, Diff)   │  │ Terminal (xterm)  │  │
│  └────────────┬────────────┘  └────────┬─────────┘  └─────────┬─────────┘  │
│               │                        │                      │            │
│  ┌────────────┴────────────┐  ┌────────┴─────────┐  ┌─────────┴─────────┐  │
│  │ Migration Workspace UI  │  │ Impact Graph UI  │  │ AI Chat & Agent   │  │
│  │ (Config, Progress, Diff)│  │ (Interactive)    │  │ (Console/Panel)   │  │
│  └────────────┬────────────┘  └────────┬─────────┘  └─────────┬─────────┘  │
└───────────────┼────────────────────────┼──────────────────────┼────────────┘
                │                        │                      │
                ▼                        ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BACKEND API LAYER (FastAPI / Uvicorn)                 │
│  ┌───────────────────┐  ┌────────────────────┐  ┌────────────────────────┐ │
│  │ Workspace & FS    │  │ Terminal (PyWinPTY)│  │ Search & Impact        │ │
│  │ (/api/workspace)  │  │ (/ws/terminal)     │  │ (/api/search,/impact)  │ │
│  └─────────┬─────────┘  └─────────┬──────────┘  └───────────┬────────────┘ │
│            │                      │                         │              │
│  ┌─────────┴─────────┐  ┌─────────┴──────────┐  ┌───────────┴────────────┐ │
│  │ Analysis Engine   │  │ Development Agent  │  │ Validation & Source    │ │
│  │ (/api/analysis)   │  │ (/api/agent)       │  │ (/api/validation,source)│ │
│  └─────────┬─────────┘  └─────────┬──────────┘  └───────────┬────────────┘ │
│            │                      │                         │              │
│  ┌─────────┴──────────────────────┴─────────────────────────┴────────────┐ │
│  │ Migration Pipeline Engine (/api/migration/*)                          │ │
│  │ (Analysis -> Generation -> Validation -> Apply -> Rollback)            │ │
│  └────────────────────────────────┬──────────────────────────────────────┘ │
└───────────────────────────────────┼────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AI PROVIDER AGNOSTIC LAYER                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ Ollama       │ │ Gemini       │ │ Groq         │ │ OpenAI / OpenRouter│   │
│  │ (Local LLM)  │ │ (Google Cloud│ │ (Fast LPU)   │ │ / Azure / Local    │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────────────┘   │
│  └─ BaseLLMProvider Interface (Dynamic Config & Failover to AST scrapper)─┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Subsystem Breakdown

### 4.1 Brownfield Development Environment
1. **IDE Workspace & Monaco Editor**: Provides browser-based multi-tab code editing, syntax highlighting, diff comparison, and directory tree navigation with lazy loading. Supports local project folders and zip archive ingestion.
2. **Integrated Terminal**: Native PTY-backed terminal streaming interactive shell sessions over WebSockets.
3. **Project Analysis Engine**: Deterministic AST and static analysis engine that categorizes codebase structure, module dependencies, three-tier architecture layers (Presentation, Business, Data), and component types (Controllers, Services, Repositories, Models, DTOs, Entities, Utilities, Tests).
4. **Intelligent Code Search**: Structural and keyword search across AST symbols, class signatures, function definitions, and REST routes.
5. **Architecture Impact Analysis**: Builds a full dependency graph (nodes and edges) for files, classes, methods, and API routes. Calculates change risk scores (Low, Medium, High) and dependent impact paths prior to editing.
6. **Development Agent**: Transforms natural-language developer requests into proposed change bundles with unified diff patches. Automatically classifies developer intent into Feature Enhancement, Bug Fixing, or Code Refactoring.
7. **Validation & Source Update Engine**: Runs a 6-pass static safety validation pipeline. Tracks user approvals and writes change bundles transactionally to disk with automatic pre-write backups and instant undo capability.

### 4.2 AI Code Migration Agent
1. **Migration Workspace**: Responsive side-by-side UI layout housing migration configuration, target scope selector, live step-by-step progress panel, code diff viewer, and history console.
2. **Migration Analysis Engine**: Analyzes legacy projects across 6 configurable migration scopes (`Current File`, `Selected Folder`, `Frontend Layer`, `Backend Layer`, `Database Layer`, `Entire Project`).
3. **AI Migration Generation Engine**: Transforms legacy source code into target languages using the active AI Provider. Writes generated code exclusively into an isolated staging workspace (`~/.brownfield-ide/migrations/<session_id>/`).
4. **6-Pass Migration Validation Engine**: Evaluates staged code for syntax correctness, architectural consistency, missing dependencies, database schema alignment, configuration validity, and risk level.
5. **Transactional Apply Engine**: Backs up target files to `~/.brownfield-ide/backups/<migration_id>/` and writes approved migrated code into the active project.
6. **Byte-for-Byte Rollback Engine**: Reverts any applied migration to its exact pre-migration state using pre-apply backup snapshots.
7. **Migration Orchestrator**: Manages state transitions, workflow progression, live status streaming, and historical logging.

---

## 5. End-to-End User Workflows

### Workflow 1: Brownfield Development & Feature Enhancement
```
Open Project / ZIP Archive
          │
          ▼
Automatic Static Project Analysis
          │
          ▼
Explore Codebase / Inspect Impact Graph / Search AST Symbols
          │
          ▼
Submit Prompt to Development Agent ("Add /healthz route")
          │
          ▼
Agent Classifies Intent & Generates Proposed Diff Bundle (In Memory)
          │
          ▼
Run 6-Pass Safety Validation -> View Risk & Impact Score
          │
          ▼
User Approves Bundle -> Transactional Apply with Backup
          │
          ▼
Workspace Auto-Refreshed (Optional Undo available)
```

### Workflow 2: Automated AI Code Migration
```
Select Migration Configuration (Target Language, Scope, Strategy)
          │
          ▼
Phase 2: Run Migration Analysis -> View Component & Asset Breakdown
          │
          ▼
Phase 3: Trigger AI Generation -> Code Staged in Isolated Directory (~/.brownfield-ide/)
          │
          ▼
Phase 4: Run 6-Pass Migration Validation -> Review Diffs & Risk Score -> Approve Files
          │
          ▼
Phase 5: Apply Migration -> Backup Snapshot Created -> Code Written to Project
          │
          ▼
Phase 6: Verification -> Live Status / History Logged (Instant Rollback available)
```
