/**
 * api.js — HTTP and WebSocket client layer for the Brownfield IDE.
 *
 * All communication with the FastAPI backend goes through this module.
 * Extension point: future AI phases will add new method groups here.
 */

const API = (() => {
  const BASE = `${window.location.protocol}//${window.location.host}`;
  const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;

  // ---------------------------------------------------------------------------
  // Core HTTP helpers
  // ---------------------------------------------------------------------------

  async function _request(method, path, { body, params, signal } = {}) {
    let url = `${BASE}${path}`;
    if (params) {
      const qs = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null)
      );
      if (qs.toString()) url += '?' + qs.toString();
    }

    const opts = {
      method,
      headers: {},
      signal,
    };

    if (body !== undefined) {
      if (body instanceof FormData) {
        opts.body = body; // Don't set Content-Type — browser will add boundary
      } else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }

    const res = await fetch(url, opts);

    if (!res.ok) {
      let errorData;
      try { errorData = await res.json(); } catch { errorData = { error: res.statusText }; }
      const msg = errorData.detail || errorData.error || `HTTP ${res.status}`;
      throw new Error(msg);
    }

    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return res.json();
    return res.text();
  }

  const get    = (path, opts)        => _request('GET',    path, opts);
  const post   = (path, body, opts)  => _request('POST',   path, { body, ...opts });
  const put    = (path, body, opts)  => _request('PUT',    path, { body, ...opts });
  const patch  = (path, body, opts)  => _request('PATCH',  path, { body, ...opts });
  const del    = (path, opts)        => _request('DELETE', path, opts);

  // ---------------------------------------------------------------------------
  // Filesystem
  // ---------------------------------------------------------------------------

  const fs = {
    /** Get shallow project tree (lazy-loading root). */
    tree: (depth = 1)            => get('/api/fs/tree', { params: { depth } }),

    /** Get one level of children for a directory. */
    children: (path)             => get('/api/fs/children', { params: { path } }),

    /** Read a file's content. */
    readFile: (path)             => get('/api/fs/file', { params: { path } }),

    /** Save a file. */
    writeFile: (path, content)   => put('/api/fs/file', { path, content }),

    /** Create a new empty file. */
    createFile: (path)           => post('/api/fs/file', { path }),

    /** Create a new folder. */
    createFolder: (path)         => post('/api/fs/folder', { path }),

    /** Delete a file or folder. */
    deleteItem: (path)           => del('/api/fs/item', { params: { path } }),

    /** Rename a file or folder. */
    rename: (path, new_name)     => patch('/api/fs/rename', { path, new_name }),

    /** Search files by name. */
    search: (q, max_results=100) => get('/api/fs/search', { params: { q, max_results } }),

    /** Upload and extract a ZIP project. Returns { project_name, project_path, tree }. */
    uploadZip: (file, destination = null) => {
      const form = new FormData();
      form.append('file', file);
      return _request('POST', '/api/fs/upload-zip', {
        body: form,
        params: destination ? { destination } : {},
      });
    },
  };

  // ---------------------------------------------------------------------------
  // Workspace
  // ---------------------------------------------------------------------------

  const workspace = {
    /** Get current workspace state. */
    state: ()           => get('/api/workspace/state'),

    /** Open a project by absolute path. */
    open: (path)        => post('/api/workspace/open', { path }),

    /** Close the current project. */
    close: ()           => post('/api/workspace/close'),

    /** List recently opened projects. */
    recent: ()          => get('/api/workspace/recent'),

    /** Remove a recent project entry. */
    removeRecent: (path)=> del('/api/workspace/recent', { params: { path } }),
  };

  // ---------------------------------------------------------------------------
  // Terminal
  // ---------------------------------------------------------------------------

  const terminal = {
    /** Create a terminal session. Returns { session_id, cwd }. */
    create: (cwd = null, cols = 80, rows = 24) =>
      post('/api/terminal/create', { cwd, cols, rows }),

    /** Kill a terminal session. */
    kill: (sessionId)   => del(`/api/terminal/${sessionId}`),

    /** List active sessions. */
    sessions: ()        => get('/api/terminal/sessions'),

    /**
     * Open a WebSocket for a terminal session.
     * Returns the WebSocket instance.
     */
    connect: (sessionId) => {
      const ws = new WebSocket(`${WS_BASE}/ws/terminal/${sessionId}`);
      return ws;
    },
  };

  // ---------------------------------------------------------------------------
  // Health
  // ---------------------------------------------------------------------------

  const health = () => get('/api/health');

  // ---------------------------------------------------------------------------
  // Extension Points (future phases)
  // ---------------------------------------------------------------------------
  // Phase 2: Analysis
  const analysis = {
    analyze: () => post('/api/analysis/analyze'),
    status: ()  => get('/api/analysis/status'),
    explain: (scope, target, active_file = null, cursor_line = null) =>
      post('/api/analysis/explain', { scope, target, active_file, cursor_line })
  };

  // Phase 3: Search
  const search = {
    query: (q) => get('/api/search', { params: { q } }),
    references: (symbol) => get('/api/search/references', { params: { symbol } })
  };

  // Phase 4: Impact Analysis
  const impact = {
    analyze: (type, target) => get('/api/impact/analyze', { params: { type, target } }),
    graph: () => get('/api/impact/graph'),
    risk: (target) => get('/api/impact/risk', { params: { target } })
  };

  // Phase 5: Development Agent
  const agent = {
    develop: (request) => post('/api/agent/develop', { request }),
    result: (planId) => get(`/api/agent/result/${planId}`),
    providers: () => get('/api/agent/providers')
  };

  // Phase 6: Validation & Approval
  const validation = {
    validate: (planId, force = false) => post('/api/validation/validate', { plan_id: planId, force }),
    report: (planId) => get(`/api/validation/report/${planId}`),
    approve: (planId) => post('/api/validation/approve', { plan_id: planId }),
    reject: (planId) => post('/api/validation/reject', { plan_id: planId }),
    decision: (planId) => get(`/api/validation/decision/${planId}`)
  };

  // Phase 7: Source Code Update
  const source = {
    apply: (planId, commit = false) => post('/api/source/apply', { plan_id: planId, commit }),
    undo: () => post('/api/source/undo'),
    rollback: (operationId) => post('/api/source/rollback', { operation_id: operationId }),
    history: () => get('/api/source/history'),
    backups: () => get('/api/source/backups'),
    gitStatus: () => get('/api/source/git-status')
  };

  // Phase 2: Code Migration Agent Analysis
  // Phase 3: AI Migration Agent (code generation)
  const migration = {
    // --- Phase 2: Analysis Engine ---
    analyze: (scope, target_path, source_lang, target_lang, strategies, source_version = null, target_version = null) =>
      post('/api/migration/analyze', { scope, target_path, source_lang, target_lang, strategies, source_version, target_version }),
    status: () => get('/api/migration/status'),
    plan: () => get('/api/migration/plan'),

    // --- Phase 3: AI Migration Agent ---
    generate: (scope, target_path, source_lang, target_lang, strategies, max_files = 40, source_version = null, target_version = null) =>
      post('/api/migration/generate', { scope, target_path, source_lang, target_lang, strategies, max_files, source_version, target_version }),
    generateStatus: () => get('/api/migration/generate/status'),
    generatedFile: (path) => get('/api/migration/generate/file', { params: { path } }),
    handoff: () => get('/api/migration/generate/handoff'),
    resetGeneration: () => post('/api/migration/generate/reset'),

    // --- Downloads ---
    downloadProjectUrl: () => '/api/migration/download/project',
    downloadFolderUrl: (path) => `/api/migration/download/folder?path=${encodeURIComponent(path)}`,
    downloadFileUrl: (path) => `/api/migration/download/file?path=${encodeURIComponent(path)}`,
    downloadInfo: (type = 'project', path = null) => get('/api/migration/download/info', { params: { type, path } }),

    // --- Phase 4: Migration Validation & Approval ---
    validate: () => post('/api/migration/validate'),
    validateStatus: () => get('/api/migration/validate/status'),
    validateFile: (path) => get('/api/migration/validate/file', { params: { path } }),
    approveFile: (path) => post('/api/migration/validate/approve', { path }),
    rejectFile: (path) => post('/api/migration/validate/reject', { path }),
    approveAllSafe: () => post('/api/migration/validate/approve-safe'),
    rejectMigration: () => post('/api/migration/validate/reject-all'),
    approvalOutput: () => get('/api/migration/validate/approval'),
    resetValidation: () => post('/api/migration/validate/reset'),

    // --- Phase 5: Migration Application (apply / rollback / history) ---
    changes: () => get('/api/migration/changes'),
    apply: (applied_by = null) => post('/api/migration/apply', { applied_by }),
    rollback: (migration_id, file = null) => post('/api/migration/rollback', { migration_id, file }),
    history: () => get('/api/migration/history'),

    // --- Phase 6: Migration Orchestrator Workflow ---
    startWorkflow: (scope, target_path, source_lang, target_lang, strategies, auto_apply = false, source_version = null, target_version = null) =>
      post('/api/migration/workflow/start', { scope, target_path, source_lang, target_lang, strategies, auto_apply, source_version, target_version }),
    workflowStatus: () => get('/api/migration/workflow/status'),
    cancelWorkflow: () => post('/api/migration/workflow/cancel'),
    dashboard: () => get('/api/migration/workflow/dashboard'),
    archivedReport: (migration_id) => get(`/api/migration/workflow/history/${migration_id}/report`)
  };

  return { fs, workspace, terminal, health, analysis, search, impact, agent, validation, source, migration };
})();
