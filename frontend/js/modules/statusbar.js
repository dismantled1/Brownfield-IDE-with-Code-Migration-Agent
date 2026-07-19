/**
 * statusbar.js — IDE status bar at the bottom of the screen.
 */

const StatusBar = (() => {
  let _els = {};
  let _state = {
    language: 'Plain Text',
    line: 1, col: 1,
    project: null,
    encoding: 'UTF-8',
    connected: true,
  };

  function init() {
    _els = {
      project:    document.getElementById('sb-project'),
      language:   document.getElementById('sb-language'),
      position:   document.getElementById('sb-position'),
      encoding:   document.getElementById('sb-encoding'),
      connection: document.getElementById('sb-connection'),
    };

    EventBus.on('statusbar:update', update);
    EventBus.on('project:opened',   d => update({ project: d.projectName }));
    EventBus.on('project:closed',   () => update({ project: null, language: 'Plain Text' }));
    EventBus.on('file:open',        d => update({ language: _langLabel(d.language), line: 1, col: 1 }));

    _render();
  }

  function update(data = {}) {
    Object.assign(_state, data);
    _render();
  }

  function _langLabel(lang) {
    const map = {
      javascript: 'JavaScript', typescript: 'TypeScript', python: 'Python',
      java: 'Java', html: 'HTML', css: 'CSS', json: 'JSON', yaml: 'YAML',
      xml: 'XML', markdown: 'Markdown', sql: 'SQL', shell: 'Shell',
      bat: 'Batch', powershell: 'PowerShell', plaintext: 'Plain Text',
      kotlin: 'Kotlin', csharp: 'C#', cpp: 'C++', c: 'C', go: 'Go',
      rust: 'Rust', ruby: 'Ruby', php: 'PHP', swift: 'Swift',
      scss: 'SCSS', less: 'Less',
    };
    return map[lang] || lang || 'Plain Text';
  }

  function _render() {
    if (_els.project)   _els.project.textContent   = _state.project || 'No project';
    if (_els.language)  _els.language.textContent  = _state.language;
    if (_els.position)  _els.position.textContent  = `Ln ${_state.line}, Col ${_state.col}`;
    if (_els.encoding)  _els.encoding.textContent  = _state.encoding;
    if (_els.connection) {
      _els.connection.textContent = _state.connected ? '● Connected' : '○ Disconnected';
      _els.connection.style.opacity = _state.connected ? '1' : '0.6';
    }
  }

  function setCursorPosition(line, col) {
    update({ line, col });
  }

  return { init, update, setCursorPosition };
})();
