/**
 * workspace.js — State persistence using localStorage.
 * Saves and restores: open project, open tabs, active tab, expanded folders.
 */

const WorkspaceState = (() => {
  const KEY = 'brownfield-ide-state';

  const defaults = () => ({
    projectPath:     null,
    projectName:     null,
    openTabs:        [],   // [{ path, name, language, isDirty }]
    activeTab:       null, // path
    expandedFolders: [],   // relative paths
    terminalSessions:[],   // session IDs
    sidebarWidth:    260,
    chatWidth:       300,
    terminalHeight:  220,
  });

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return defaults();
      return { ...defaults(), ...JSON.parse(raw) };
    } catch { return defaults(); }
  }

  function save(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) {
      console.warn('[WorkspaceState] Could not persist state:', e);
    }
  }

  let _state = load();

  return {
    get()            { return _state; },

    setProject(path, name) {
      _state.projectPath = path;
      _state.projectName = name;
      save(_state);
    },

    clearProject() {
      _state.projectPath = null;
      _state.projectName = null;
      _state.openTabs    = [];
      _state.activeTab   = null;
      _state.expandedFolders = [];
      save(_state);
    },

    addTab(tab) {
      const exists = _state.openTabs.find(t => t.path === tab.path);
      if (!exists) {
        _state.openTabs.push(tab);
        save(_state);
      }
    },

    updateTab(path, updates) {
      const tab = _state.openTabs.find(t => t.path === path);
      if (tab) {
        Object.assign(tab, updates);
        save(_state);
      }
    },

    removeTab(path) {
      _state.openTabs    = _state.openTabs.filter(t => t.path !== path);
      if (_state.activeTab === path) {
        _state.activeTab = _state.openTabs.length
          ? _state.openTabs[_state.openTabs.length - 1].path
          : null;
      }
      save(_state);
    },

    setActiveTab(path) {
      _state.activeTab = path;
      save(_state);
    },

    setExpandedFolders(paths) {
      _state.expandedFolders = paths;
      save(_state);
    },

    addExpandedFolder(path) {
      if (!_state.expandedFolders.includes(path)) {
        _state.expandedFolders.push(path);
        save(_state);
      }
    },

    removeExpandedFolder(path) {
      _state.expandedFolders = _state.expandedFolders.filter(p => p !== path);
      save(_state);
    },

    setSidebarWidth(w)    { _state.sidebarWidth    = w; save(_state); },
    setChatWidth(w)       { _state.chatWidth        = w; save(_state); },
    setTerminalHeight(h)  { _state.terminalHeight   = h; save(_state); },

    reset() { _state = defaults(); save(_state); },
  };
})();
