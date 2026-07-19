/**
 * migration_agent.js — UI Module for the AI Migration Agent (Phase 3).
 *
 * Drives AI code generation from the Phase 2 Migration Plan:
 *   - Triggers /api/migration/generate and polls /generate/status.
 *   - Renders the real generation progress checklist (replaces Phase 2 progress
 *     during generation).
 *   - Renders the Generated Files explorer (folder hierarchy + status badges).
 *   - Renders the read-only code comparison view (unified + split, syntax
 *     highlighted).
 *
 * The original project is never modified — generated code lives in an isolated
 * staging workspace on the backend. This module is read-only over that output.
 */

const MigrationAgent = (() => {
  let _pollInterval = null;
  let _files = [];            // latest file metadata list
  let _activeFilter = 'all';  // all | new | modified | skipped | failed
  let _selectedPath = null;
  let _diffView = 'split';    // split | unified
  let _lastDetail = null;     // cached GeneratedFile detail for re-render on toggle
  let _started = false;

  // Fixed generation steps — must mirror GENERATION_STEPS in the backend.
  const GENERATION_STEPS = [
    "Preparing AI Context",
    "Loading Migration Plan",
    "Loading Provider",
    "Generating Controllers",
    "Generating Services",
    "Generating Repositories",
    "Generating Models",
    "Generating Configuration",
    "Generating Build Files",
    "Building Generated Project",
    "Migration Generation Completed"
  ];

  // Broad, multi-language keyword set for lightweight diff highlighting.
  const KEYWORDS = new Set([
    "abstract","async","await","base","bool","boolean","break","byte","case","catch",
    "char","class","const","continue","def","default","del","do","double","elif","else",
    "enum","except","export","extends","false","final","finally","float","fn","for","from",
    "func","function","global","go","goto","if","impl","implements","import","in","include",
    "int","interface","is","lambda","let","long","match","mod","module","mut","namespace",
    "new","nil","none","not","null","or","override","package","pass","private","protected",
    "public","pub","raise","readonly","record","ref","return","self","short","static","str",
    "string","struct","super","switch","this","throw","throws","trait","true","try","type",
    "typeof","use","using","val","var","virtual","void","when","where","while","with","yield","and"
  ]);

  // ---------------------------------------------------------------------------
  // Init & bindings
  // ---------------------------------------------------------------------------

  function init() {
    document.getElementById('btn-diff-split')?.addEventListener('click', () => _setDiffView('split'));
    document.getElementById('btn-diff-unified')?.addEventListener('click', () => _setDiffView('unified'));

    document.getElementById('btn-download-file')?.addEventListener('click', _downloadFile);
    document.getElementById('btn-download-folder')?.addEventListener('click', _downloadFolder);
    document.getElementById('btn-download-project')?.addEventListener('click', _downloadProject);

    document.getElementById('migration-gen-filters')?.addEventListener('click', (e) => {
      const chip = e.target.closest('.migration-gen-filter');
      if (!chip) return;
      _activeFilter = chip.dataset.filter || 'all';
      document.querySelectorAll('.migration-gen-filter').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      _renderTree();
    });

    EventBus.on('project:closed', reset);
  }

  function _downloadFile() {
    if (!_selectedPath) {
      Toast.show('Select a generated file to download.', 'warning');
      return;
    }
    const url = API.migration.downloadFileUrl(_selectedPath);
    _triggerDownload(url);
  }

  function _downloadFolder() {
    let folder = '';
    if (_selectedPath && _selectedPath.includes('/')) {
      folder = _selectedPath.substring(0, _selectedPath.lastIndexOf('/'));
    }
    const url = API.migration.downloadFolderUrl(folder);
    _triggerDownload(url);
  }

  function _downloadProject() {
    const url = API.migration.downloadProjectUrl();
    _triggerDownload(url);
  }

  function _triggerDownload(url) {
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    Toast.show('Starting ZIP download…', 'info', 2000);
  }

  // ---------------------------------------------------------------------------
  // Public entry — called by migration.js once Phase 2 analysis completes
  // ---------------------------------------------------------------------------

  async function begin(plan, config) {
    if (!plan || !config) return;
    _stopPolling();
    _resetState();
    _started = true;

    const section = document.getElementById('migration-gen-section');
    if (section) section.style.display = 'block';

    const modeText = config.isLatestVersionMode ? `${plan.source_language} → Latest Version` : `${plan.source_language} → ${_targetName(config.targetLang)}`;
    _setMeta(`Preparing migration: ${modeText} · scope: ${config.scope}`);
    _setStatus('Starting AI Migration…', 'warning');
    _resetProgressPanel();
    _renderGenSteps({ step_logs: [], current_step: 'Preparing AI Context', status: 'generating' });

    try {
      await API.migration.generate(
        config.scope, config.targetPath, config.sourceLang, config.targetLang, config.strategies, 40, config.sourceVer, config.targetVer
      );
      _startPolling();
    } catch (err) {
      console.error('[MigrationAgent] generate trigger failed:', err);
      _setStatus('Generation Failed', 'error');
      Toast.show(`AI Migration failed to start: ${err.message}`, 'error');
    }
  }

  function reset() {
    _stopPolling();
    _resetState();
    const section = document.getElementById('migration-gen-section');
    if (section) section.style.display = 'none';
    // Cascade: tear down Phase 4 validation output too.
    if (typeof MigrationValidation !== 'undefined') MigrationValidation.reset();
  }

  function _resetState() {
    _files = [];
    _activeFilter = 'all';
    _selectedPath = null;
    _lastDetail = null;
    _started = false;
    const tree = document.getElementById('migration-gen-tree');
    if (tree) tree.innerHTML = '';
    const diff = document.getElementById('migration-diff-body');
    if (diff) diff.innerHTML = '<div class="migration-diff-empty">Select a generated file to compare.</div>';
    const title = document.getElementById('migration-diff-title');
    if (title) title.textContent = 'Code Comparison';
    _updateFilterCounts({ new_files: 0, modified_files: 0, skipped_files: 0, failed_files: 0, files_selected: 0 });
  }

  // ---------------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------------

  function _startPolling() {
    _stopPolling();
    _pollStatus();
    _pollInterval = setInterval(_pollStatus, 500);
  }

  function _stopPolling() {
    if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
  }

  async function _pollStatus() {
    try {
      const data = await API.migration.generateStatus();
      _applyStatus(data);

      if (data.status === 'completed') {
        _stopPolling();
        _onCompleted(data);
      } else if (data.status === 'failed') {
        _stopPolling();
        _setStatus('Generation Failed', 'error');
        Toast.show(`AI Migration error: ${data.error || 'Unknown error'}`, 'error');
      }
    } catch (err) {
      console.warn('[MigrationAgent] poll failed:', err);
    }
  }

  function _applyStatus(data) {
    // Progress bar (reuses the Phase 2 progress bar — replaces its content).
    const bar = document.getElementById('migration-progress-bar');
    if (bar) bar.style.width = `${Math.max(data.progress || 0, 4)}%`;

    _renderGenSteps(data);

    // Live meta line.
    const providerLabel = data.provider ? ` · provider: ${data.provider}` : '';
    if (data.current_file && data.status === 'generating') {
      _setMeta(`Generating: ${data.current_file}${providerLabel}`);
      _setStatus('Generating Code…', 'warning');
    }

    // Summary counters (share the Phase 2 summary cards).
    const s = data.summary || {};
    _setCounter('stat-files-converted', s.files_generated);
    _setCounter('stat-warnings', s.warnings);
    _setCounter('stat-errors', s.errors);
    _updateFilterCounts(s);

    // Explorer — update live as files stream in.
    _files = data.files || [];
    _renderTree();
    _updateDownloadInfo(data);
  }

  function _onCompleted(data) {
    const s = data.summary || {};
    _setStatus('Migration Completed', 'success');
    const stagePart = data.staging_path ? ` · staged at ${data.staging_path}` : '';
    _setMeta(
      `Done — ${s.new_files || 0} new, ${s.modified_files || 0} modified, ` +
      `${s.skipped_files || 0} skipped, ${s.failed_files || 0} failed` +
      ` · provider: ${data.provider || 'offline'}${stagePart}`
    );
    Toast.show('AI Migration generation completed ✓', 'success');

    _updateDownloadInfo(data);

    // Auto-select the first generated (new/modified) file for comparison.
    const first = _files.find(f => f.status === 'new' || f.status === 'modified');
    if (first) _selectFile(first.generated_path);

    // Phase 4: reveal the validation workspace now that code exists.
    if (typeof MigrationValidation !== 'undefined') MigrationValidation.onGenerationComplete(data);
  }

  async function _updateDownloadInfo(data) {
    const displayEl = document.getElementById('migration-staging-path-display');
    const badgeEl = document.getElementById('migration-zip-size-badge');
    if (displayEl && data && data.staging_path) {
      displayEl.textContent = data.staging_path;
    }
    try {
      const info = await API.migration.downloadInfo('project');
      if (info && info.success && badgeEl) {
        badgeEl.textContent = `ZIP: ${info.formatted_zip_size} (${info.file_count} files)`;
      }
    } catch (e) {
      // ignore non-critical errors during polling
    }
  }

  // ---------------------------------------------------------------------------
  // Progress checklist (mirrors migration.js style, generation steps)
  // ---------------------------------------------------------------------------

  function _renderGenSteps(data) {
    const stepsLog = document.getElementById('migration-steps-log');
    if (!stepsLog) return;

    const logs = data.step_logs || [];
    const logged = new Set(logs.map(l => l.step));
    const current = data.current_step;
    const done = data.status === 'completed';
    const failed = data.status === 'failed';

    stepsLog.innerHTML = '';
    GENERATION_STEPS.forEach((name) => {
      let dotClass = 'waiting';
      if (done) {
        dotClass = logged.has(name) ? 'completed' : 'waiting';
      } else if (name === current) {
        dotClass = failed ? 'error' : 'running';
      } else if (logged.has(name)) {
        dotClass = 'completed';
      }

      const last = [...logs].reverse().find(l => l.step === name);
      const timeText = last ? (last.timestamp || '') : '';

      const row = document.createElement('div');
      row.className = `migration-step-row${dotClass === 'running' ? ' active' : ''}`;
      row.innerHTML = `
        <span class="migration-step-dot ${dotClass}"></span>
        <span class="migration-step-text">${Helpers.escapeHtml(name)}</span>
        <span class="migration-step-time">${timeText}</span>
      `;
      stepsLog.appendChild(row);
    });
  }

  // ---------------------------------------------------------------------------
  // Generated Files explorer
  // ---------------------------------------------------------------------------

  function _filteredFiles() {
    if (_activeFilter === 'all') return _files;
    return _files.filter(f => f.status === _activeFilter);
  }

  function _renderTree() {
    const container = document.getElementById('migration-gen-tree');
    if (!container) return;

    const files = _filteredFiles();
    if (!files.length) {
      container.innerHTML = `<div class="migration-gen-empty">${
        _files.length ? 'No files match this filter.' : 'Waiting for generated files…'
      }</div>`;
      return;
    }

    const tree = _buildTree(files);
    container.innerHTML = '';
    container.appendChild(_renderNode(tree, 0));
  }

  function _buildTree(files) {
    const root = { name: '', dirs: {}, files: [] };
    files.forEach(f => {
      const parts = f.generated_path.split('/');
      let node = root;
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        node.dirs[part] = node.dirs[part] || { name: part, dirs: {}, files: [] };
        node = node.dirs[part];
      }
      node.files.push(f);
    });
    return root;
  }

  function _renderNode(node, depth) {
    const frag = document.createDocumentFragment();

    Object.keys(node.dirs).sort().forEach(dirName => {
      const dir = node.dirs[dirName];
      const row = document.createElement('div');
      row.className = 'migration-gen-folder';
      row.style.paddingLeft = `${depth * 12 + 4}px`;
      row.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span>${Helpers.escapeHtml(dirName)}</span>`;
      frag.appendChild(row);
      frag.appendChild(_renderNode(dir, depth + 1));
    });

    node.files.slice().sort((a, b) => a.generated_path.localeCompare(b.generated_path)).forEach(f => {
      const name = f.generated_path.split('/').pop();
      const row = document.createElement('div');
      row.className = 'migration-gen-file' + (f.generated_path === _selectedPath ? ' selected' : '');
      row.style.paddingLeft = `${depth * 12 + 6}px`;
      const clickable = (f.status === 'new' || f.status === 'modified' || f.status === 'failed');
      if (!clickable) row.classList.add('disabled');

      const counts = (f.additions || f.removals)
        ? `<span class="migration-gen-counts"><span class="add">+${f.additions || 0}</span> <span class="rem">-${f.removals || 0}</span></span>`
        : '';

      row.innerHTML = `
        <span class="migration-gen-badge ${f.status}" title="${f.status}">${_badgeLetter(f.status)}</span>
        <span class="migration-gen-name" title="${Helpers.escapeHtml(f.generated_path)}">${Helpers.escapeHtml(name)}</span>
        ${counts}`;

      if (clickable) {
        row.addEventListener('click', () => _selectFile(f.generated_path));
      } else if (f.reason) {
        row.title = f.reason;
      }
      frag.appendChild(row);
    });

    return frag;
  }

  function _badgeLetter(status) {
    return { new: 'N', modified: 'M', skipped: 'S', failed: 'F' }[status] || '?';
  }

  function _updateFilterCounts(s) {
    _setChipCount('all', s.files_selected);
    _setChipCount('new', s.new_files);
    _setChipCount('modified', s.modified_files);
    _setChipCount('skipped', s.skipped_files);
    _setChipCount('failed', s.failed_files);
  }

  function _setChipCount(filter, value) {
    const el = document.querySelector(`.migration-gen-filter[data-filter="${filter}"] .count`);
    if (el) el.textContent = (value === undefined || value === null) ? '0' : value;
  }

  // ---------------------------------------------------------------------------
  // Code comparison (diff) view
  // ---------------------------------------------------------------------------

  async function _selectFile(path) {
    _selectedPath = path;
    _renderTree();  // refresh selection highlight

    const title = document.getElementById('migration-diff-title');
    const body = document.getElementById('migration-diff-body');
    if (title) title.textContent = path;
    if (body) body.innerHTML = '<div class="migration-diff-empty">Loading comparison…</div>';

    try {
      const res = await API.migration.generatedFile(path);
      _lastDetail = res.file;
      _renderDiff(_lastDetail);
    } catch (err) {
      if (body) body.innerHTML = `<div class="migration-diff-empty error">Failed to load file: ${Helpers.escapeHtml(err.message)}</div>`;
    }
  }

  function _setDiffView(view) {
    _diffView = view;
    document.getElementById('btn-diff-split')?.classList.toggle('active', view === 'split');
    document.getElementById('btn-diff-unified')?.classList.toggle('active', view === 'unified');
    if (_lastDetail) _renderDiff(_lastDetail);
  }

  function _renderDiff(file) {
    const body = document.getElementById('migration-diff-body');
    if (!body) return;

    if (file.error) {
      body.innerHTML = `<div class="migration-diff-empty error">⚠ ${Helpers.escapeHtml(file.error)}</div>`;
      return;
    }
    const rows = file.diff_rows || [];
    if (!rows.length) {
      body.innerHTML = '<div class="migration-diff-empty">No differences to display.</div>';
      return;
    }

    const lang = file.language || 'plaintext';
    body.innerHTML = _diffView === 'split' ? _renderSplit(rows, lang) : _renderUnified(rows, lang);
  }

  function _renderSplit(rows, lang) {
    let left = '', right = '';
    rows.forEach(r => {
      const lClass = (r.type === 'remove' || r.type === 'modify') ? r.type : (r.type === 'add' ? 'empty' : 'equal');
      const rClass = (r.type === 'add' || r.type === 'modify') ? r.type : (r.type === 'remove' ? 'empty' : 'equal');
      left += _codeLine(r.left_num, r.left, lClass, lang, r.left === undefined || r.left === null);
      right += _codeLine(r.right_num, r.right, rClass, lang, r.right === undefined || r.right === null);
    });
    return `
      <div class="migration-diff-split">
        <div class="migration-diff-col"><div class="migration-diff-colhead">Original</div>${left}</div>
        <div class="migration-diff-col"><div class="migration-diff-colhead">Generated</div>${right}</div>
      </div>`;
  }

  function _renderUnified(rows, lang) {
    let html = '';
    rows.forEach(r => {
      if (r.type === 'equal') {
        html += _uLine(r.left_num, r.right_num, ' ', r.left, 'equal', lang);
      } else if (r.type === 'remove') {
        html += _uLine(r.left_num, '', '-', r.left, 'remove', lang);
      } else if (r.type === 'add') {
        html += _uLine('', r.right_num, '+', r.right, 'add', lang);
      } else if (r.type === 'modify') {
        html += _uLine(r.left_num, '', '-', r.left, 'remove', lang);
        html += _uLine('', r.right_num, '+', r.right, 'add', lang);
      }
    });
    return `<div class="migration-diff-unified">${html}</div>`;
  }

  function _codeLine(num, text, cls, lang, empty) {
    if (empty) return `<div class="migration-code-line empty"><span class="ln"></span><span class="code"></span></div>`;
    return `<div class="migration-code-line ${cls}"><span class="ln">${num || ''}</span><span class="code">${_highlight(text || '', lang)}</span></div>`;
  }

  function _uLine(lnum, rnum, sign, text, cls, lang) {
    return `<div class="migration-code-line ${cls}">` +
      `<span class="ln">${lnum || ''}</span><span class="ln">${rnum || ''}</span>` +
      `<span class="sign">${sign}</span>` +
      `<span class="code">${_highlight(text || '', lang)}</span></div>`;
  }

  // ---------------------------------------------------------------------------
  // Lightweight syntax highlighting (read-only preview)
  // ---------------------------------------------------------------------------

  function _highlight(line, lang) {
    if (!line) return '';
    try {
      const hashComment = ['python', 'ruby', 'yaml', 'shell', 'bat'].includes(lang);
      const parts = hashComment
        ? ['#[^\\n]*']
        : ['\\/\\/[^\\n]*', '\\/\\*[\\s\\S]*?\\*\\/'];
      const commentRe = parts.join('|');
      const re = new RegExp(
        `(${commentRe})` +
        `|("(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\`(?:\\\\.|[^\`\\\\])*\`)` +
        `|(\\b\\d[\\d._]*\\b)` +
        `|([A-Za-z_$][A-Za-z0-9_$]*)`,
        'g'
      );
      let out = '', last = 0, m;
      while ((m = re.exec(line)) !== null) {
        out += _esc(line.slice(last, m.index));
        if (m[1]) out += `<span class="tok-com">${_esc(m[1])}</span>`;
        else if (m[2]) out += `<span class="tok-str">${_esc(m[2])}</span>`;
        else if (m[3]) out += `<span class="tok-num">${_esc(m[3])}</span>`;
        else if (m[4]) out += KEYWORDS.has(m[4]) ? `<span class="tok-kw">${_esc(m[4])}</span>` : _esc(m[4]);
        last = re.lastIndex;
        if (re.lastIndex === m.index) re.lastIndex++;  // guard against zero-length matches
      }
      out += _esc(line.slice(last));
      return out;
    } catch (e) {
      return _esc(line);
    }
  }

  function _esc(s) {
    return Helpers.escapeHtml(String(s));
  }

  // ---------------------------------------------------------------------------
  // Small DOM helpers
  // ---------------------------------------------------------------------------

  function _setMeta(text) {
    const el = document.getElementById('migration-gen-meta');
    if (el) el.textContent = text;
  }

  function _setStatus(text, cls) {
    const el = document.getElementById('stat-current-status');
    if (el) {
      el.textContent = text;
      el.className = 'migration-stat-value' + (cls ? ' ' + cls : '');
    }
  }

  function _setCounter(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = (value === undefined || value === null) ? 0 : value;
  }

  function _resetProgressPanel() {
    const bar = document.getElementById('migration-progress-bar');
    if (bar) bar.style.width = '4%';
  }

  function _targetName(code) {
    const map = {
      java: 'Java', python: 'Python', csharp: 'C#', javascript: 'JavaScript',
      typescript: 'TypeScript', go: 'Go', rust: 'Rust', cpp: 'C++', php: 'PHP', other: 'Other'
    };
    return map[(code || '').toLowerCase()] || code || 'Target';
  }

  return { init, begin, reset };
})();
