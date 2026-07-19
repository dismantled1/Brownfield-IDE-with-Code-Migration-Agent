/**
 * app.js — Main application entry point for the Brownfield IDE.
 *
 * Responsibilities:
 *  1. Initialize all modules
 *  2. Set up panel resize handles
 *  3. Wire up header buttons
 *  4. Restore workspace state on load
 *  5. Load Monaco Editor (async CDN)
 */

// ---------------------------------------------------------------------------
// Toast notification system (global)
// ---------------------------------------------------------------------------

const Toast = (() => {
  function show(message, type = 'info', duration = 3500) {
    EventBus.emit('toast:show', { message, type, duration });
  }
  return { show };
})();

// Internal toast renderer
(function initToastRenderer() {
  EventBus.on('toast:show', ({ message, type, duration = 3500 }) => {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const iconMap = {
      success: Icons.getUI('success'),
      error:   Icons.getUI('error'),
      warning: Icons.getUI('warning'),
      info:    Icons.getUI('info'),
    };

    const toast = Helpers.el('div', { class: `toast ${type}` });
    toast.innerHTML = (iconMap[type] || '') + `<span>${Helpers.escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 400);
    }, duration);

    toast.addEventListener('click', () => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 400);
    });
  });
})();

// ---------------------------------------------------------------------------
// Panel Resize Handles
// ---------------------------------------------------------------------------

function _initResizeHandles() {
  // Sidebar (horizontal)
  _makeHResizable(
    document.getElementById('sidebar-resize'),
    document.getElementById('sidebar-panel'),
    WorkspaceState.get().sidebarWidth,
    WorkspaceState.setSidebarWidth.bind(WorkspaceState),
    { min: 160, max: 480, cssVar: '--sidebar-width' }
  );

  // Chat panel (horizontal, right side)
  _makeHResizable(
    document.getElementById('chat-resize'),
    document.getElementById('chat-panel'),
    WorkspaceState.get().chatWidth,
    WorkspaceState.setChatWidth.bind(WorkspaceState),
    { min: 220, max: 500, cssVar: '--chat-width', direction: 'right' }
  );
}

function _makeHResizable(handle, panel, initialWidth, onResize, { min, max, cssVar, direction = 'left' }) {
  if (!handle || !panel) return;

  panel.style.width = initialWidth + 'px';
  if (cssVar) document.documentElement.style.setProperty(cssVar, initialWidth + 'px');

  let startX, startW;

  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = e.clientX;
    startW = panel.getBoundingClientRect().width;
    handle.classList.add('dragging');

    const onMove = e => {
      const delta = direction === 'right' ? startX - e.clientX : e.clientX - startX;
      const newW  = Helpers.clamp(startW + delta, min, max);
      panel.style.width = newW + 'px';
      if (cssVar) document.documentElement.style.setProperty(cssVar, newW + 'px');
      onResize(newW);
      if (typeof Editor !== 'undefined') Editor.layout();
    };

    const onUp = () => {
      handle.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  });
}

// ---------------------------------------------------------------------------
// Header buttons
// ---------------------------------------------------------------------------

function _initHeaderButtons() {
  document.getElementById('btn-header-open-folder')?.addEventListener('click', WelcomeScreen.showOpenFolderDialog);
  document.getElementById('btn-header-open-zip')?.addEventListener('click', WelcomeScreen.showOpenZipDialog);
  document.getElementById('btn-header-close')?.addEventListener('click', async () => {
    const ok = await Helpers.confirmModal({
      title: 'Close Project',
      message: 'Close the current project? Unsaved changes will be lost.',
      confirmText: 'Close',
      danger: true,
    });
    if (!ok) return;
    await API.workspace.close();
    EventBus.emit('project:closed');
  });

  document.getElementById('btn-new-terminal')?.addEventListener('click', () => {
    TerminalManager.createSession();
  });
}

// ---------------------------------------------------------------------------
// Layout show/hide helpers (safe with inline styles)
// ---------------------------------------------------------------------------

function _showIDE()     { document.getElementById('ide-layout').style.display = 'flex'; }
function _hideIDE()     { document.getElementById('ide-layout').style.display = 'none'; }
function _showWelcome() { document.getElementById('welcome-screen').style.display = 'flex'; }
function _hideWelcome() { document.getElementById('welcome-screen').style.display = 'none'; }

// ---------------------------------------------------------------------------
// Project lifecycle events
// ---------------------------------------------------------------------------

function _initProjectEvents() {
  EventBus.on('project:opened', ({ projectName, projectPath }) => {
    const current = WorkspaceState.get();
    if (current.projectPath && current.projectPath !== projectPath) {
      WorkspaceState.clearProject();
    }
    WorkspaceState.setProject(projectPath, projectName);
    _hideWelcome();
    _showIDE();
    EventBus.emit('statusbar:update', { project: projectName });
    Toast.show(`Opened "${projectName}"`, 'success');
  });

  EventBus.on('project:closed', () => {
    WorkspaceState.clearProject();
    _hideIDE();
    _showWelcome();
    EventBus.emit('statusbar:update', { project: null });
  });
}

// ---------------------------------------------------------------------------
// Workspace restore
// ---------------------------------------------------------------------------

async function _restoreWorkspace() {
  const state = WorkspaceState.get();

  // Restore panel sizes
  const sidebar = document.getElementById('sidebar-panel');
  const chat    = document.getElementById('chat-panel');
  const terminal = document.getElementById('terminal-panel');

  if (sidebar  && state.sidebarWidth)   { sidebar.style.width  = state.sidebarWidth  + 'px'; }
  if (chat     && state.chatWidth)      { chat.style.width     = state.chatWidth     + 'px'; }
  if (terminal && state.terminalHeight) { terminal.style.height = state.terminalHeight + 'px'; }

  if (!state.projectPath) return;

  // Try to reopen the project
  try {
    const result = await API.workspace.open(state.projectPath);
    EventBus.emit('project:opened', {
      projectName: result.project_name,
      projectPath: result.project_path,
      tree:        result.tree,
    });

    // Restore tabs after project opens
    if (state.openTabs?.length) {
      EventBus.emit('workspace:restore', { state });
    }
  } catch (err) {
    console.warn('[App] Could not restore project:', err.message);
    WorkspaceState.clearProject();
  }
}

// ---------------------------------------------------------------------------
// Monaco Loader
// ---------------------------------------------------------------------------

function _loadMonaco() {
  require.config({
    paths: { 'vs': 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' },
  });

  window.MonacoEnvironment = {
    getWorkerUrl: () => URL.createObjectURL(new Blob([`
      self.MonacoEnvironment = { baseUrl: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/' };
      importScripts('https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/base/worker/workerMain.js');
    `], { type: 'text/javascript' })),
  };

  require(['vs/editor/editor.main'], function(monaco) {
    Editor.init(monaco);
    console.log('[App] Monaco Editor loaded ✓');
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Brownfield IDE] Booting Phase 1…');

  // Ensure correct initial display states
  _hideIDE();
  _showWelcome();

  // Init modules
  StatusBar.init();
  ChatPanel.init();
  WelcomeScreen.init();
  TabBar.init();
  Explorer.init();
  TerminalManager.init();
  Analysis.init();
  Search.init();
  Impact.init();
  Agent.init();
  Validation.init();
  Source.init();
  Migration.init();
  MigrationAgent.init();
  MigrationValidation.init();
  MigrationApply.init();
  MigrationOrchestrator.init();

  // Init layout
  _initResizeHandles();
  _initHeaderButtons();
  _initProjectEvents();

  // Load Monaco
  _loadMonaco();

  // Restore workspace (shows IDE if project exists)
  await _restoreWorkspace();

  console.log('[Brownfield IDE] Phase 2 ready ✓');
});
