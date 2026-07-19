/**
 * agent.js — Phase 5 Development Agent UI.
 *
 * Renders the DEVELOPMENT PLAN sidebar panel (request, files to modify/create/
 * delete, risk, generated changes, validation) and a Diff Viewer (unified +
 * split) for previewing each proposed patch. The agent only proposes changes —
 * nothing here writes to project files.
 */

const Agent = (() => {
  let _activeProject = null;
  let _bundle = null;          // last develop() result
  let _patchesByPath = {};     // path -> patch
  let _diffMode = 'unified';
  let _currentPatch = null;

  function init() {
    _bindAccordion();
    _bindDiffViewer();
    _clearUI();

    EventBus.on('project:opened', ({ projectPath }) => {
      _activeProject = projectPath;
      _bundle = null;
      _clearUI();
    });
    EventBus.on('project:closed', () => {
      _activeProject = null;
      _bundle = null;
      _clearUI();
      _closeDiffViewer();
    });

    // Chat (or any caller) signals a request is in flight / completed.
    EventBus.on('agent:trigger', ({ request }) => {
      _expandPanel();
      _showLoading(request);
    });
    EventBus.on('agent:result', ({ bundle }) => {
      _bundle = bundle;
      _indexPatches(bundle);
      _expandPanel();
      _renderPanel(bundle);
    });
    EventBus.on('agent:error', ({ message }) => _renderError(message));
  }

  function _bindAccordion() {
    const header = document.getElementById('header-devplan');
    const panel = document.getElementById('section-devplan');
    if (header && panel) {
      header.addEventListener('click', () => panel.classList.toggle('collapsed'));
    }
  }

  function _expandPanel() {
    const panel = document.getElementById('section-devplan');
    if (panel) panel.classList.remove('collapsed');
  }

  function _indexPatches(bundle) {
    _patchesByPath = {};
    (bundle.patches || []).forEach(p => { _patchesByPath[p.path] = p; });
  }

  // ---------------------------------------------------------------------------
  // Panel rendering
  // ---------------------------------------------------------------------------

  function _clearUI() {
    const c = document.getElementById('devplan-panel-content');
    if (c) c.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No development request yet</div>`;
  }

  function _showLoading(request) {
    const c = document.getElementById('devplan-panel-content');
    if (!c) return;
    c.innerHTML = `
      <div class="analysis-progress-wrapper" style="background:rgba(16,185,129,0.05); border:1px solid rgba(16,185,129,0.15)">
        <div class="progress-label" style="color:var(--color-success)"><span>Development Agent working…</span></div>
        <div class="progress-track"><div class="progress-bar" style="width:55%; background:linear-gradient(90deg,#10b981,#059669)"></div></div>
        <div class="progress-status-text" title="${Helpers.escapeHtml(request || '')}">Selecting context, planning, generating patches…</div>
      </div>`;
  }

  function _renderError(msg) {
    const c = document.getElementById('devplan-panel-content');
    if (c) c.innerHTML = `<div style="color:var(--color-error); padding:5px 0;">Agent failed: ${Helpers.escapeHtml(msg || 'unknown error')}</div>`;
  }

  function _renderPanel(bundle) {
    const c = document.getElementById('devplan-panel-content');
    if (!c) return;
    const esc = Helpers.escapeHtml;

    const plan = bundle.plan || {};
    const risk = bundle.risk || { level: 'Low', explanation: '' };
    const stats = bundle.stats || {};
    const val = bundle.validation || { summary: {} };
    const intentBadge = `<span class="agent-intent-badge ${esc(bundle.intent)}">${esc(bundle.intent)}</span>`;
    const providerBadge = `<span class="agent-provider-badge" title="Model provider">${esc(bundle.provider)}</span>`;
    const riskPill = `<span class="risk-badge ${esc((risk.level || 'low').toLowerCase())}">● ${esc(risk.level)} Risk</span>`;

    c.innerHTML = `
      <div class="agent-card">
        <div class="agent-card-row">
          ${intentBadge}${providerBadge}${riskPill}
        </div>
        <div class="agent-request" title="${esc(bundle.request)}">${esc(bundle.request)}</div>
        ${bundle.understanding ? `<div class="agent-understanding">${esc(bundle.understanding)}</div>` : ''}
      </div>

      ${_fileGroup('Files to Modify', plan.files_to_modify, 'modify')}
      ${_fileGroup('Files to Create', plan.files_to_create, 'create')}
      ${_fileGroup('Files to Delete', plan.files_to_delete, 'delete')}
      ${plan.tests_to_update && plan.tests_to_update.length ? _fileGroup('Tests to Update', plan.tests_to_update, 'test') : ''}

      ${plan.steps && plan.steps.length ? `
      <div class="agent-group-header"><span>Implementation Steps</span></div>
      <ol class="agent-steps">${plan.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}

      <div class="agent-group-header">
        <span>Generated Changes</span>
        <span class="impact-group-count">${(bundle.patches || []).length}</span>
      </div>
      <div class="agent-changes-list">${_changesList(bundle.patches || [])}</div>

      <div class="agent-validation ${val.summary.failed ? 'has-fail' : (val.summary.warnings ? 'has-warn' : 'all-pass')}">
        <span>Validation:</span>
        <span class="agent-val-pass">✓ ${val.summary.passed || 0}</span>
        <span class="agent-val-warn">⚠ ${val.summary.warnings || 0}</span>
        <span class="agent-val-fail">✗ ${val.summary.failed || 0}</span>
      </div>

      <div class="agent-footer-note">
        +${stats.additions || 0} / −${stats.removals || 0} lines · ${bundle.next_phase && bundle.next_phase.ready_for_validation ? 'Ready for Phase 6 (approval)' : 'Has validation failures'} · not yet applied
      </div>
    `;

    // Bind change-row clicks → diff viewer
    c.querySelectorAll('.agent-change-row[data-path]').forEach(row => {
      row.addEventListener('click', () => _openDiffForPath(row.dataset.path));
    });
  }

  function _fileGroup(title, items, type) {
    items = items || [];
    if (!items.length) return '';
    const esc = Helpers.escapeHtml;
    const rows = items.map(f => {
      const name = esc((typeof f === 'string' ? f : (f.to || f.path || '')).split('/').pop());
      const full = esc(typeof f === 'string' ? f : (f.to || f.path || ''));
      return `<a class="agent-file-link ${type}" title="${full}"><span class="agent-file-dot ${type}"></span><span>${name}</span></a>`;
    }).join('');
    return `
      <div class="agent-group-header"><span>${esc(title)}</span><span class="impact-group-count">${items.length}</span></div>
      <div class="agent-file-list">${rows}</div>`;
  }

  function _changesList(patches) {
    if (!patches.length) {
      return `<div style="font-style:italic; color:var(--color-text-muted); font-size:10px; padding:4px;">No changes generated</div>`;
    }
    const esc = Helpers.escapeHtml;
    return patches.map(p => {
      const name = esc(p.path.split('/').pop());
      return `
        <div class="agent-change-row" data-path="${esc(p.path)}" title="Click to view diff: ${esc(p.path)}">
          <span class="diff-change-badge ${esc(p.change_type)}">${esc(p.change_type)}</span>
          <span class="agent-change-name">${name}</span>
          <span class="agent-change-stat"><span class="add">+${p.additions}</span> <span class="del">−${p.removals}</span></span>
        </div>`;
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // Diff Viewer
  // ---------------------------------------------------------------------------

  function _bindDiffViewer() {
    document.getElementById('diff-viewer-close')?.addEventListener('click', _closeDiffViewer);
    document.getElementById('diff-viewer-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'diff-viewer-overlay') _closeDiffViewer();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        const ov = document.getElementById('diff-viewer-overlay');
        if (ov && ov.style.display !== 'none') _closeDiffViewer();
      }
    });
    ['unified', 'split'].forEach(mode => {
      document.getElementById(`diff-toggle-${mode}`)?.addEventListener('click', () => {
        _diffMode = mode;
        document.querySelectorAll('.diff-toggle-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
        if (_currentPatch) _renderDiffBody(_currentPatch);
      });
    });
  }

  function _openDiffForPath(path) {
    const patch = _patchesByPath[path];
    if (patch) openDiff(patch);
  }

  function openDiff(patch) {
    _currentPatch = patch;
    const overlay = document.getElementById('diff-viewer-overlay');
    if (!overlay) return;
    document.getElementById('diff-viewer-filename').textContent = patch.path;
    const badge = document.getElementById('diff-viewer-change-type');
    badge.textContent = patch.change_type;
    badge.className = `diff-change-badge ${patch.change_type}`;
    _renderDiffBody(patch);
    overlay.style.display = 'flex';
  }

  function _closeDiffViewer() {
    const overlay = document.getElementById('diff-viewer-overlay');
    if (overlay) overlay.style.display = 'none';
    _currentPatch = null;
  }

  function _renderDiffBody(patch) {
    const body = document.getElementById('diff-viewer-body');
    if (!body) return;
    body.className = `diff-viewer-body ${_diffMode}`;
    body.innerHTML = _diffMode === 'split' ? _renderSplit(patch) : _renderUnified(patch.diff);
  }

  function _renderUnified(diffText) {
    const esc = Helpers.escapeHtml;
    if (!diffText) return `<div class="diff-empty">No textual changes.</div>`;
    const rows = diffText.split('\n').map(line => {
      if (line.startsWith('+++') || line.startsWith('---')) return '';
      let cls = 'ctx';
      if (line.startsWith('@@')) cls = 'hunk';
      else if (line.startsWith('+')) cls = 'add';
      else if (line.startsWith('-')) cls = 'del';
      return `<div class="diff-line ${cls}"><span class="diff-line-text">${esc(line || ' ')}</span></div>`;
    }).join('');
    return `<div class="diff-unified">${rows}</div>`;
  }

  function _renderSplit(patch) {
    const esc = Helpers.escapeHtml;
    const rows = _diffToRows(patch.diff);
    if (!rows.length) return `<div class="diff-empty">No textual changes.</div>`;
    const html = rows.map(r => {
      if (r.hunk) {
        return `<div class="diff-split-row hunk"><div class="diff-split-cell hunk" colspan="2">${esc(r.hunk)}</div></div>`;
      }
      const lt = r.leftType, rt = r.rightType;
      return `
        <div class="diff-split-row">
          <div class="diff-split-cell ${lt}">${r.left != null ? esc(r.left || ' ') : ''}</div>
          <div class="diff-split-cell ${rt}">${r.right != null ? esc(r.right || ' ') : ''}</div>
        </div>`;
    }).join('');
    return `
      <div class="diff-split-head"><div>Before</div><div>After</div></div>
      <div class="diff-split">${html}</div>`;
  }

  // Convert a unified diff into aligned before/after rows for split view.
  function _diffToRows(diffText) {
    const rows = [];
    let rem = [], add = [];
    const flush = () => {
      const n = Math.max(rem.length, add.length);
      for (let i = 0; i < n; i++) {
        rows.push({
          left: i < rem.length ? rem[i] : null, leftType: i < rem.length ? 'del' : 'empty',
          right: i < add.length ? add[i] : null, rightType: i < add.length ? 'add' : 'empty',
        });
      }
      rem = []; add = [];
    };
    (diffText || '').split('\n').forEach(line => {
      if (line.startsWith('+++') || line.startsWith('---')) return;
      if (line.startsWith('@@')) { flush(); rows.push({ hunk: line }); return; }
      if (line.startsWith('-')) { rem.push(line.slice(1)); return; }
      if (line.startsWith('+')) { add.push(line.slice(1)); return; }
      flush();
      const t = line.startsWith(' ') ? line.slice(1) : line;
      rows.push({ left: t, leftType: 'ctx', right: t, rightType: 'ctx' });
    });
    flush();
    return rows;
  }

  return { init, openDiff };
})();

// Bind globally for direct calls
window.Agent = Agent;
