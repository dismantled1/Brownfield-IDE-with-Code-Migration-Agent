/**
 * editor.js — Monaco Editor wrapper for the Brownfield IDE.
 *
 * Manages multiple editor models (one per open file), syntax highlighting,
 * auto-save, keyboard shortcuts, and cursor tracking.
 */

const Editor = (() => {
  let _monaco  = null;  // Monaco module reference
  let _editor  = null;  // Monaco editor instance
  let _models  = {};    // path → Monaco ITextModel
  let _currentPath = null;
  let _saveTimers  = {};

  // ---------------------------------------------------------------------------
  // Init — called after Monaco is loaded
  // ---------------------------------------------------------------------------

  function init(monaco) {
    _monaco = monaco;

    // Create the editor with our dark theme
    monaco.editor.defineTheme('brownfield-dark', {
      base:    'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment',   foreground: '6a9955', fontStyle: 'italic' },
        { token: 'keyword',   foreground: 'c586c0' },
        { token: 'string',    foreground: 'ce9178' },
        { token: 'number',    foreground: 'b5cea8' },
        { token: 'type',      foreground: '4ec9b0' },
        { token: 'class',     foreground: '4ec9b0' },
        { token: 'function',  foreground: 'dcdcaa' },
        { token: 'variable',  foreground: '9cdcfe' },
        { token: 'operator',  foreground: 'd4d4d4' },
      ],
      colors: {
        'editor.background':           '#12121e',
        'editor.foreground':           '#e2e8f0',
        'editorLineNumber.foreground': '#4a4a6a',
        'editorLineNumber.activeForeground': '#7c3aed',
        'editor.selectionBackground':  '#7c3aed40',
        'editor.inactiveSelectionBackground': '#7c3aed20',
        'editorCursor.foreground':     '#7c3aed',
        'editorCursor.background':     '#12121e',
        'editor.lineHighlightBackground': '#1e1e35',
        'editorGutter.background':     '#12121e',
        'editorWidget.background':     '#1a1a2e',
        'editorWidget.border':         '#2a2a4a',
        'input.background':            '#12121e',
        'input.border':                '#2a2a4a',
        'focusBorder':                 '#7c3aed',
        'scrollbar.shadow':            '#00000000',
        'scrollbarSlider.background':  '#38386080',
        'scrollbarSlider.hoverBackground': '#4c4c8080',
        'scrollbarSlider.activeBackground': '#7c3aed80',
        'minimap.background':          '#0d0d14',
        'editorOverviewRuler.border':  '#2a2a4a',
        'dropdown.background':         '#1a1a2e',
        'dropdown.border':             '#2a2a4a',
        'list.hoverBackground':        '#1e1e35',
        'list.activeSelectionBackground': '#7c3aed40',
      },
    });

    _editor = monaco.editor.create(
      document.getElementById('monaco-container'),
      {
        theme:           'brownfield-dark',
        language:        'plaintext',
        fontSize:        14,
        fontFamily:      "'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace",
        fontLigatures:   true,
        lineNumbers:     'on',
        minimap:         { enabled: true, maxColumn: 80 },
        scrollBeyondLastLine: false,
        wordWrap:        'off',
        automaticLayout: true,
        tabSize:         2,
        insertSpaces:    true,
        formatOnType:    true,
        formatOnPaste:   true,
        bracketPairColorization: { enabled: true },
        renderWhitespace:'selection',
        smoothScrolling: true,
        cursorBlinking:  'smooth',
        cursorSmoothCaretAnimation: 'on',
        folding:         true,
        foldingStrategy:'indentation',
        renderLineHighlight: 'all',
        suggest:         { showIcons: true },
        padding:         { top: 12, bottom: 12 },
        overviewRulerLanes: 3,
        scrollbar: {
          useShadows: false,
          verticalScrollbarSize: 6,
          horizontalScrollbarSize: 6,
        },
      }
    );

    // Cursor position → status bar
    _editor.onDidChangeCursorPosition(e => {
      StatusBar.setCursorPosition(e.position.lineNumber, e.position.column);
    });

    // Track dirty state
    _editor.onDidChangeModelContent(() => {
      if (!_currentPath) return;
      const isDirty = _isModelDirty(_currentPath);
      EventBus.emit('editor:change', { path: _currentPath, isDirty });
      // Auto-save after 2 s of inactivity
      clearTimeout(_saveTimers[_currentPath]);
      _saveTimers[_currentPath] = setTimeout(() => _autoSave(_currentPath), 2000);
    });

    // Keyboard shortcuts
    // Ctrl+S — save
    _editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
      () => { if (_currentPath) _save(_currentPath); }
    );
    // Ctrl+Shift+S — save all
    _editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyS,
      _saveAll
    );

    // EventBus integration
    EventBus.on('file:open',         _onFileOpen);
    EventBus.on('tab:activate',      ({ path }) => _activateModel(path));
    EventBus.on('file:deleted',      ({ path }) => _closeModel(path));
    EventBus.on('file:renamed',      ({ oldPath, newPath }) => _renameModel(oldPath, newPath));
    EventBus.on('editor:showWelcome', _showWelcome);
    EventBus.on('project:closed',    _closeAll);

    // Restore tabs from state
    EventBus.on('workspace:restore', _restoreTabs);

    EventBus.emit('editor:ready');
  }

  // ---------------------------------------------------------------------------
  // Model management
  // ---------------------------------------------------------------------------

  function _onFileOpen(data) {
    const { path, name, language, content } = data;

    if (!_models[path]) {
      const uri   = _monaco.Uri.parse(`file:///${path}`);
      const lang  = language || 'plaintext';
      const model = _monaco.editor.createModel(content || '', lang, uri);

      // Store original content for dirty tracking
      model._originalContent = content || '';
      _models[path] = model;
    }

    _activateModel(path);
    _hideWelcome();
    _editor.focus();
  }

  function _activateModel(path) {
    if (!_models[path]) return;
    _currentPath = path;
    _editor.setModel(_models[path]);
    _editor.focus();

    const tab = TabBar.getTabs().find(t => t.path === path);
    if (tab) {
      StatusBar.update({ language: tab.language || 'plaintext' });
    }
  }

  function _closeModel(path) {
    const model = _models[path];
    if (model) {
      model.dispose();
      delete _models[path];
    }
    if (_currentPath === path) {
      _currentPath = null;
    }
  }

  function _renameModel(oldPath, newPath) {
    const model = _models[oldPath];
    if (!model) return;
    delete _models[oldPath];

    const newModel = _monaco.editor.createModel(
      model.getValue(),
      model.getLanguageId(),
      _monaco.Uri.parse(`file:///${newPath}`)
    );
    newModel._originalContent = model._originalContent;
    _models[newPath] = newModel;
    model.dispose();

    if (_currentPath === oldPath) {
      _currentPath = newPath;
      _editor.setModel(_models[newPath]);
    }
  }

  function _closeAll() {
    Object.keys(_models).forEach(p => _closeModel(p));
    _currentPath = null;
    _showWelcome();
  }

  // ---------------------------------------------------------------------------
  // Dirty tracking
  // ---------------------------------------------------------------------------

  function _isModelDirty(path) {
    const model = _models[path];
    if (!model) return false;
    return model.getValue() !== model._originalContent;
  }

  // ---------------------------------------------------------------------------
  // Save
  // ---------------------------------------------------------------------------

  async function _save(path) {
    const model = _models[path];
    if (!model) return;

    try {
      const content = model.getValue();
      await API.fs.writeFile(path, content);
      model._originalContent = content;
      EventBus.emit('file:saved', { path });
      Toast.show('Saved', 'success');
    } catch (err) {
      Toast.show(`Save failed: ${err.message}`, 'error');
    }
  }

  async function _autoSave(path) {
    if (_isModelDirty(path)) {
      await _save(path).catch(() => {});
    }
  }

  function _saveAll() {
    Object.keys(_models).forEach(path => {
      if (_isModelDirty(path)) _save(path);
    });
  }

  // ---------------------------------------------------------------------------
  // Welcome screen
  // ---------------------------------------------------------------------------

  function _showWelcome() {
    Helpers.show(document.getElementById('editor-welcome'));
    Helpers.hide(document.getElementById('monaco-container'));
  }

  function _hideWelcome() {
    Helpers.hide(document.getElementById('editor-welcome'));
    Helpers.show(document.getElementById('monaco-container'));
  }

  // ---------------------------------------------------------------------------
  // Restore from WorkspaceState
  // ---------------------------------------------------------------------------

  async function _restoreTabs({ state }) {
    if (!state.openTabs?.length) { _showWelcome(); return; }

    const deadTabs = [];
    for (const tab of state.openTabs) {
      try {
        const data = await API.fs.readFile(tab.path);
        if (data && data.content !== undefined) {
          _onFileOpen({ path: data.path, name: tab.name, language: data.language, content: data.content });
        } else {
          deadTabs.push(tab.path);
        }
      } catch {
        deadTabs.push(tab.path);
      }
    }

    deadTabs.forEach(path => WorkspaceState.removeTab(path));

    if (state.activeTab && _models[state.activeTab]) {
      _activateModel(state.activeTab);
    }
  }

  // ---------------------------------------------------------------------------
  // Resize
  // ---------------------------------------------------------------------------

  function layout() {
    if (_editor) _editor.layout();
  }

  function getActiveFilePath() {
    return _currentPath;
  }

  function getCursorPosition() {
    if (!_editor) return null;
    const pos = _editor.getPosition();
    return pos ? { lineNumber: pos.lineNumber, column: pos.column } : null;
  }

  function openAndHighlight(path, lineNumber) {
    if (_models[path]) {
      _activateModel(path);
      _highlightLine(lineNumber);
    } else {
      API.fs.readFile(path).then(data => {
        _onFileOpen({
          path: data.path,
          name: path.split('/').pop(),
          language: data.language,
          content: data.content
        });
        _highlightLine(lineNumber);
      }).catch(err => {
        Toast.show(`Could not open file: ${err.message}`, 'error');
      });
    }
  }

  /**
   * Refresh open editor models from disk for the given paths (used after the
   * Source Update Engine applies changes). Re-reads content and resets the
   * dirty baseline; closes models whose files were deleted.
   */
  async function refreshOpenFiles(paths) {
    if (!Array.isArray(paths)) return;
    for (const path of paths) {
      const model = _models[path];
      if (!model) continue;
      try {
        const data = await API.fs.readFile(path);
        if (model.getValue() !== data.content) model.setValue(data.content);
        model._originalContent = data.content;
        EventBus.emit('editor:change', { path, isDirty: false });
      } catch {
        // File was deleted on disk — drop its tab/model.
        EventBus.emit('file:close', { path });
        _closeModel(path);
      }
    }
  }

  function _highlightLine(lineNumber) {
    if (!_editor || !lineNumber) return;
    
    const model = _editor.getModel();
    if (!model) return;
    const lineCount = model.getLineCount();
    const targetLine = Math.min(Math.max(1, lineNumber), lineCount);

    setTimeout(() => {
      _editor.revealLineInCenter(targetLine);
      _editor.setPosition({ lineNumber: targetLine, column: 1 });
      _editor.focus();

      // Highlight line
      const range = new _monaco.Range(targetLine, 1, targetLine, 1);
      const newDecorations = _editor.deltaDecorations(_editor.oldDecorations || [], [
        {
          range: range,
          options: {
            isWholeLine: true,
            className: 'line-highlight-flash',
            marginClassName: 'line-highlight-margin'
          }
        }
      ]);
      _editor.oldDecorations = newDecorations;

      // Clear the line highlight after 1.5s
      setTimeout(() => {
        if (_editor && _editor.oldDecorations === newDecorations) {
          _editor.deltaDecorations(newDecorations, []);
          _editor.oldDecorations = [];
        }
      }, 1500);
    }, 100);
  }

  return { init, layout, getActiveFilePath, getCursorPosition, openAndHighlight, refreshOpenFiles };
})();
