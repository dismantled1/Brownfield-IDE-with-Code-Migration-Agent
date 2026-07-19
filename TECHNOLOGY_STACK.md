# Agentic Brownfield Development Environment & AI Code Migration Agent
## Complete Technology Stack Documentation

This document details all programming languages, frameworks, libraries, tools, and runtime environments powering the project.

---

## 1. Programming Languages

### 1.1 Core System Languages
* **Python 3.10+**: Core backend service logic, FastAPI routing, AST parsing, static analysis engines, PTY management, and file system abstractions.
* **JavaScript (ES6+)**: Frontend application logic, UI modules, dynamic DOM manipulation, WebSocket handling, and event orchestration.
* **HTML5 & CSS3**: Semantic UI structure, custom dark-mode design system, glassmorphism aesthetics, flexbox/grid layouts, and responsive media queries.

### 1.2 Language Support (Analysis & Migration Targets)
The platform parses, analyzes, and transforms code across the following target languages:
* **Python** (`.py`)
* **Java** (`.java`)
* **C#** (`.cs`)
* **JavaScript / TypeScript** (`.js`, `.jsx`, `.ts`, `.tsx`)
* **Go** (`.go`)
* **Rust** (`.rs`)
* **C / C++** (`.c`, `.cpp`, `.cc`, `.h`, `.hpp`)
* **PHP** (`.php`)
* **Kotlin** (`.kt`, `.kts`)
* **Ruby** (`.rb`)
* **Swift** (`.swift`)

---

## 2. Backend Architecture & Technologies

### 2.1 Backend Framework
* **FastAPI**: Modern, high-performance web framework for building RESTful APIs and WebSocket handlers.
* **Uvicorn**: Asynchronous Server Gateway Interface (ASGI) server for running FastAPI applications.
* **Pydantic v2**: High-speed data validation and settings management using Python type annotations.
* **Starlette**: Underpinnings for ASGI web services, WebSocket connections, and background task scheduling.

### 2.2 Core Python Libraries & Dependencies
* **httpx**: Asynchronous HTTP client for communicating with external LLM provider APIs.
* **urllib3 / requests**: Synchronous HTTP networking for local provider probing and health checks.
* **pywinpty**: Python bindings for the Windows Pseudoconsole (ConPTY) API to run real interactive shells (`cmd.exe`, `powershell.exe`, `bash.exe`).
* **pty / termios**: Standard POSIX pseudoterminal interface for Linux/macOS execution.
* **asyncio**: Asynchronous I/O event loops for concurrency without multithreading overhead.
* **ast**: Built-in Python Abstract Syntax Tree module for structural parsing, class extraction, and call graph construction.
* **difflib**: Unified and aligend line-by-line diff generation for code comparisons.

---

## 3. Frontend Architecture & Technologies

### 3.1 Core UI Framework
* **Vanilla HTML5 & CSS3**: High-performance UI without framework overhead or heavy bundles.
* **Modular ES6 JavaScript Modules**: 19 discrete JS modules cleanly separating concerns (`workspace.js`, `explorer.js`, `editor.js`, `terminal.js`, `analysis.js`, `search.js`, `impact.js`, `agent.js`, `validation.js`, `source.js`, `migration.js`, `migration_agent.js`, `migration_validation.js`, `migration_apply.js`, `migration_orchestrator.js`, `chat.js`, `tabs.js`, `statusbar.js`, `welcome.js`).

### 3.2 Key Frontend Libraries
* **Monaco Editor** (`monaco-editor` via CDN / local assets): VS Code's editor core supporting syntax highlighting, code editing, line numbering, diff views, and code folding.
* **xterm.js**: Full-featured terminal emulator in the browser with terminal rendering, ANSI color escapes, and WebSocket integration.
* **xterm-addon-fit**: Automatic resizing addon for adjusting terminal rows/cols to container viewports.
* **Vis.js Network / Cytoscape**: Interactive node-edge dependency graph rendering for Architecture Impact Analysis.

---

## 4. AI & LLM Integration Layer

### 4.1 AI Provider Layer Architecture
* **BaseLLMProvider Interface**: Abstract base class (`backend/services/llm/base.py`) defining standard completion and generation methods.
* **Dynamic Configuration Manager**: Centralized settings manager (`backend/services/llm/config.py`) reading and writing configuration state to `~/.brownfield-ide/settings.json`.

### 4.2 Supported LLM Providers & Models
1. **Ollama (Local)**: Local REST API at `http://localhost:11434`. Auto-detects installed models including `qwen2.5-coder:7b`, `gemma4:latest`, `llama3`, `codellama`, and `mistral`.
2. **Google Gemini**: Direct integration with Gemini 1.5 Flash / Gemini Pro endpoints via API key authentication.
3. **Groq**: LPU inference engine for rapid code completion (`llama-3.1-70b`, `mixtral-8x7b`).
4. **OpenRouter**: Unified API gateway routing to Anthropic Claude, OpenAI GPT-4, and open-source models.
5. **OpenAI**: Direct REST client for `gpt-4o`, `gpt-4-turbo`, and `gpt-3.5-turbo`.
6. **Azure OpenAI**: Enterprise Azure endpoints with deployment ID and API version parameters.
7. **Local API**: Custom OpenAI-compatible local server endpoints (e.g. LM Studio, vLLM, LocalAI).
8. **Deterministic AST Fallback Engine**: Offline code transformer for offline generation resilience when LLM providers are unreachable.

---

## 5. Storage, File System & Backups

* **Local File System**: Direct file system operations for workspace projects.
* **Isolated Staging Directory**: `~/.brownfield-ide/migrations/<session_id>/` for non-destructive code generation.
* **Pre-Apply Backup Store**: `~/.brownfield-ide/backups/<migration_id>/` storing original source files and manifest metadata.
* **Persistent Configuration Store**: `~/.brownfield-ide/settings.json` for AI provider keys and preferences.

---

## 6. Build, Test & Deployment Environment

### 6.1 Testing Frameworks
* **pytest**: Unit and integration testing runner.
* **FastAPI TestClient (httpx)**: In-process API integration testing.
* **Custom Enterprise Verification Suites**: `final_qa_addendum.py`, `end_to_end_qa_audit.py`, `enterprise_audit_suite.py`, `final_production_verification.py`.

### 6.2 Supported Operating Systems
* **Windows 10 / 11** (Fully supported with native PTY via PyWinPTY).
* **Linux** (Ubuntu, Debian, Fedora, RHEL via POSIX PTY).
* **macOS** (macOS 12+ Intel & Apple Silicon via POSIX PTY).

### 6.3 Browser Compatibility
* **Google Chrome / Chromium**: Version 100+ (Recommended).
* **Microsoft Edge**: Version 100+.
* **Mozilla Firefox**: Version 100+.
* **Apple Safari**: Version 15+.
