/**
 * tabs.js — Editor tab bar management.
 * Handles multiple open files, tab switching, closing, and unsaved indicators.
 */

const TabBar = (() => {
  const _tabs    = [];   // [{ path, name, language, isDirty }]
  let   _active  = null; // currently active path
  const _closed  = [];   // recently closed tabs (for reopen)

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    EventBus.on('file:open',    _onFileOpen);
    EventBus.on('file:close',   ({ path }) => close(path));
    EventBus.on('file:saved',   ({ path }) => _setDirty(path, false));
    EventBus.on('editor:change',({ path, isDirty }) => _setDirty(path, isDirty));
    EventBus.on('file:renamed', ({ oldPath, newPath, node }) => {
      const t = _tabs.find(t => t.path === oldPath);
      if (t) { t.path = newPath; t.name = node.name; _render(); }
    });
    EventBus.on('file:deleted', ({ path }) => close(path));

    // Keyboard shortcuts
    document.addEventListener('keydown', _onKeyDown);

    _render();
  }

  // ---------------------------------------------------------------------------
  // Core operations
  // ---------------------------------------------------------------------------

  function open(tab) {
    // tab = { path, name, language }
    const exists = _tabs.find(t => t.path === tab.path);
    if (!exists) {
      _tabs.push({ ...tab, isDirty: false });
    }
    setActive(tab.path);
  }

  function close(path) {
    const idx = _tabs.findIndex(t => t.path === path);
    if (idx === -1) return;

    const [removed] = _tabs.splice(idx, 1);
    _closed.unshift(removed);
    if (_closed.length > 20) _closed.pop();

    if (_active === path) {
      // Activate nearest tab
      const next = _tabs[idx] || _tabs[idx - 1] || null;
      _active = next ? next.path : null;
      if (_active) {
        EventBus.emit('file:open', _tabs.find(t => t.path === _active));
      } else {
        EventBus.emit('editor:showWelcome');
      }
    }
    WorkspaceState.removeTab(path);
    _render();
  }

  function setActive(path) {
    _active = path;
    WorkspaceState.setActiveTab(path);
    _render();
    const tab = _tabs.find(t => t.path === path);
    if (tab) EventBus.emit('tab:activate', tab);
  }

  function reopenLast() {
    const last = _closed.shift();
    if (last) EventBus.emit('file:open', last);
  }

  function closeAll() {
    const dirty = _tabs.filter(t => t.isDirty);
    if (dirty.length === 0) {
      _tabs.length = 0;
      _active = null;
      EventBus.emit('editor:showWelcome');
      _render();
    } else {
      Toast.show(`${dirty.length} unsaved file(s) — save them first.`, 'warning');
    }
  }

  function _setDirty(path, isDirty) {
    const tab = _tabs.find(t => t.path === path);
    if (tab && tab.isDirty !== isDirty) {
      tab.isDirty = isDirty;
      WorkspaceState.updateTab(path, { isDirty });
      _render();
    }
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  function _onFileOpen(data) {
    open({ path: data.path, name: data.name, language: data.language });
    WorkspaceState.addTab({ path: data.path, name: data.name, language: data.language });
  }

  function _onKeyDown(e) {
    const ctrl = e.ctrlKey || e.metaKey;
    if (!ctrl) return;

    if (e.key === 'w') {
      e.preventDefault();
      if (_active) close(_active);
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      const idx = _tabs.findIndex(t => t.path === _active);
      const next = e.shiftKey
        ? (idx - 1 + _tabs.length) % _tabs.length
        : (idx + 1) % _tabs.length;
      if (_tabs[next]) setActive(_tabs[next].path);
    }
    if (e.shiftKey && e.key === 'T') {
      e.preventDefault();
      reopenLast();
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  function _render() {
    const bar = document.getElementById('tab-bar-tabs');
    if (!bar) return;

    bar.innerHTML = '';

    _tabs.forEach(tab => {
      const isActive = tab.path === _active;
      const tabEl = document.createElement('div');
      tabEl.className = `editor-tab${isActive ? ' active' : ''}${tab.isDirty ? ' unsaved' : ''}`;
      tabEl.title = tab.path;
      tabEl.dataset.path = tab.path;

      tabEl.innerHTML = `
        <span class="tab-file-icon">${Icons.getFileIcon(Helpers.extname(tab.name))}</span>
        <span class="tab-name">${Helpers.escapeHtml(tab.name)}</span>
        <button class="tab-close" title="Close tab">${Icons.getUI('x')}</button>
      `;

      tabEl.addEventListener('click', e => {
        if (e.target.closest('.tab-close')) {
          e.stopPropagation();
          _confirmClose(tab);
        } else {
          setActive(tab.path);  // setActive() internally emits 'tab:activate'
        }
      });

      // Middle-click to close
      tabEl.addEventListener('mousedown', e => {
        if (e.button === 1) { e.preventDefault(); _confirmClose(tab); }
      });

      bar.appendChild(tabEl);
    });

    // Scroll active tab into view
    if (_active) {
      const activeEl = bar.querySelector(`[data-path="${CSS.escape(_active)}"]`);
      if (activeEl) activeEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
  }

  async function _confirmClose(tab) {
    if (tab.isDirty) {
      const ok = await Helpers.confirmModal({
        title: 'Unsaved Changes',
        message: `"${tab.name}" has unsaved changes. Close without saving?`,
        confirmText: 'Close',
        danger: true,
      });
      if (!ok) return;
    }
    close(tab.path);
  }

  function getTabs()   { return _tabs; }
  function getActive() { return _active; }

  return { init, open, close, setActive, closeAll, reopenLast, getTabs, getActive };
})();
