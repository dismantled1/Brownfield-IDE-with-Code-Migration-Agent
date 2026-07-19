/**
 * source.js — Phase 7 Source Code Update & Final Integration UI.
 *
 * Renders the SOURCE UPDATE panel (apply approved changes + status) and the
 * CHANGE HISTORY panel (past operations + rollback). On a successful apply/undo
 * it refreshes the workspace (explorer, analysis, search, graph) and open files.
 * This is the only module that triggers real writes to project files.
 */

const Source = (() => {
  let _activeProject = null;
  let _planId = null;
  let _request = null;
  let _ready = false;
  let _counts = { modify: 0, create: 0, delete: 0 };
  let _affected = [];
  let _git = { is_repo: false };
  let _status = null; // null | applying | success | failed | rolledback

  function init() {
    _bindAccordions();
    _clearApplyUI();
    _clearHistoryUI();

    EventBus.on('project:opened', async ({ projectPath }) => {
      _activeProject = projectPath;
      _reset();
      _clearApplyUI();
      _loadGit();
      _loadHistory();
    });
    EventBus.on('project:closed', () => {
      _activeProject = null;
      _reset();
      _clearApplyUI();
      _clearHistoryUI();
    });

    // New proposal generated → not yet approved.
    EventBus.on('agent:result', ({ bundle }) => {
      _planId = bundle.plan_id;
      _request = bundle.request;
      _ready = false;
      _status = null;
      const plan = bundle.plan || {};
      _counts = {
        modify: (plan.files_to_modify || []).length,
        create: (plan.files_to_create || []).length,
        delete: (plan.files_to_delete || []).length,
      };
      _affected = (bundle.patches || []).flatMap(p => p.new_path ? [p.path, p.new_path] : [p.path]);
      _renderApply();
    });

    // Approval state changed in the Validation panel.
    EventBus.on('source:approval', ({ planId, ready }) => {
      if (planId === _planId) {
        _ready = ready;
        if (ready) _expand('section-source');
        _renderApply();
      }
    });
  }

  function _reset() { _planId = null; _request = null; _ready = false; _status = null; _counts = { modify: 0, create: 0, delete: 0 }; _affected = []; }

  function _bindAccordions() {
    [['header-source', 'section-source'], ['header-history', 'section-history']].forEach(([h, s]) => {
      const header = document.getElementById(h), panel = document.getElementById(s);
      if (header && panel) header.addEventListener('click', () => panel.classList.toggle('collapsed'));
    });
  }

  function _expand(id) { const p = document.getElementById(id); if (p) p.classList.remove('collapsed'); }

  // ---------------------------------------------------------------------------
  // Apply
  // ---------------------------------------------------------------------------

  async function applyChanges(commit) {
    if (!_planId || !_ready) return null;
    _status = 'applying';
    _renderApply();
    let res;
    try {
      res = await API.source.apply(_planId, !!commit);
    } catch (err) {
      _status = 'failed';
      _renderApply(err.message);
      return null;
    }
    if (res.status === 'SUCCESS') {
      _status = 'success';
      _affected = res.affected_paths || _affected;
      await _refreshWorkspace(res.refresh, _affected);
      _loadHistory();
      _renderApply();
      if (typeof Toast !== 'undefined') Toast.show('Changes applied to project', 'success');
    } else {
      _status = res.status === 'ROLLED_BACK' ? 'rolledback' : 'failed';
      _renderApply(res.message || res.error);
    }
    return res;
  }

  async function undo() {
    const res = await API.source.undo();
    if (res.status === 'UNDONE') {
      await _refreshWorkspace(res.refresh, res.affected_paths || []);
      _loadHistory();
      if (typeof Toast !== 'undefined') Toast.show('Last change undone', 'success');
    }
    return res;
  }

  async function rollback(operationId) {
    const res = await API.source.rollback(operationId);
    if (res.status === 'UNDONE') {
      await _refreshWorkspace(res.refresh, res.affected_paths || []);
      _loadHistory();
      if (typeof Toast !== 'undefined') Toast.show('Operation rolled back', 'success');
    }
    return res;
  }

  async function _refreshWorkspace(refresh, affectedPaths) {
    // Explorer + analysis + graph cascade via the existing refresh event.
    EventBus.emit('explorer:refresh');
    // Update any open editor models in place.
    if (typeof Editor !== 'undefined' && affectedPaths && affectedPaths.length) {
      try { await Editor.refreshOpenFiles(affectedPaths); } catch { /* ignore */ }
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering — Apply panel
  // ---------------------------------------------------------------------------

  function _clearApplyUI() {
    const c = document.getElementById('source-panel-content');
    if (c) c.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No approved changes to apply</div>`;
  }

  function _renderApply(errorMsg) {
    const c = document.getElementById('source-panel-content');
    if (!c) return;
    if (!_planId) { _clearApplyUI(); return; }
    const esc = Helpers.escapeHtml;

    const statusBlock = {
      applying: `<div class="src-status applying">⏳ Applying changes…</div>`,
      success: `<div class="src-status success">✅ Applied successfully — workspace refreshed.</div>`,
      failed: `<div class="src-status failed">❌ ${esc(errorMsg || 'Update failed.')}</div>`,
      rolledback: `<div class="src-status rolledback">↩️ ${esc(errorMsg || 'Update failed and was rolled back.')}</div>`,
    }[_status] || (_ready
      ? `<div class="src-status ready">Approved — ready to apply.</div>`
      : `<div class="src-status waiting">Awaiting approval in the Validation panel.</div>`);

    const gitRow = _git.is_repo
      ? `<label class="src-git"><input type="checkbox" id="src-commit-chk"> Commit to git (<code>${esc(_git.branch || '?')}</code>) after apply</label>`
      : '';

    const disabled = (!_ready || _status === 'applying' || _status === 'success') ? 'disabled' : '';

    c.innerHTML = `
      <div class="src-card">
        <div class="src-request" title="${esc(_request || '')}">${esc(_request || '')}</div>
        <div class="src-counts">
          <span class="src-count mod">✏️ ${_counts.modify} modify</span>
          <span class="src-count add">➕ ${_counts.create} create</span>
          <span class="src-count del">🗑️ ${_counts.delete} delete</span>
        </div>
        ${statusBlock}
        ${gitRow}
        <button class="btn src-apply-btn" id="src-apply-btn" ${disabled}>
          ${_status === 'success' ? 'Applied ✓' : 'Apply Approved Changes'}
        </button>
        <div class="src-note">Only generated → validated → approved changes are written to disk.</div>
      </div>`;

    const btn = document.getElementById('src-apply-btn');
    if (btn && !disabled) {
      btn.addEventListener('click', () => {
        const commit = document.getElementById('src-commit-chk')?.checked;
        applyChanges(commit);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering — Change History panel
  // ---------------------------------------------------------------------------

  function _clearHistoryUI() {
    const c = document.getElementById('history-panel-content');
    if (c) c.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No changes applied yet</div>`;
  }

  async function _loadHistory() {
    const c = document.getElementById('history-panel-content');
    if (!c || !_activeProject) return;
    let data;
    try { data = await API.source.history(); }
    catch { return; }
    const ops = data.history || [];
    if (!ops.length) { _clearHistoryUI(); return; }
    const esc = Helpers.escapeHtml;

    c.innerHTML = ops.map(op => {
      const s = op.summary || {};
      const undone = op.undone;
      const badge = undone
        ? `<span class="hist-badge undone">undone</span>`
        : `<span class="hist-badge applied">applied</span>`;
      const when = Helpers.timeAgo ? Helpers.timeAgo(op.timestamp) : op.timestamp;
      const btn = undone
        ? ''
        : `<button class="btn btn-ghost hist-rollback" data-op="${esc(op.operation_id)}">Rollback</button>`;
      return `
        <div class="hist-item ${undone ? 'is-undone' : ''}">
          <div class="hist-head">
            <span class="hist-request" title="${esc(op.request)}">${esc(op.request || '(no request)')}</span>
            ${badge}
          </div>
          <div class="hist-meta">
            <span>${esc(when)}</span>
            <span class="hist-counts">✏️${s.modified || 0} ➕${s.created || 0} 🗑️${s.deleted || 0}</span>
          </div>
          ${btn}
        </div>`;
    }).join('');

    c.querySelectorAll('.hist-rollback[data-op]').forEach(b => {
      b.addEventListener('click', () => rollback(b.dataset.op));
    });
  }

  async function _loadGit() {
    try { _git = await API.source.gitStatus(); }
    catch { _git = { is_repo: false }; }
  }

  // Chat-facing helpers
  function getState() { return { planId: _planId, ready: _ready, status: _status }; }
  async function showHistory() {
    _expand('section-history');
    await _loadHistory();
    try { return (await API.source.history()).history || []; }
    catch { return []; }
  }

  return { init, applyChanges, undo, rollback, showHistory, getState };
})();

window.Source = Source;
