/**
 * validation.js — Phase 6 Validation & Approval UI.
 *
 * Renders the VALIDATION & APPROVAL sidebar panel: validation status, stage
 * results (syntax / static / dependency / tests / impact), errors & warnings,
 * risk, the final diffs (reusing the Phase 5 Diff Viewer), and Approve / Reject /
 * Regenerate controls. Auto-runs after the Development Agent produces changes.
 *
 * No source files are modified here — approval records state only.
 */

const Validation = (() => {
  let _activeProject = null;
  let _planId = null;
  let _request = null;
  let _report = null;
  let _patches = [];

  function init() {
    _bindAccordion();
    _clearUI();

    EventBus.on('project:opened', ({ projectPath }) => {
      _activeProject = projectPath;
      _reset();
      _clearUI();
    });
    EventBus.on('project:closed', () => {
      _activeProject = null;
      _reset();
      _clearUI();
    });

    // After the agent proposes changes, validate them automatically.
    EventBus.on('agent:result', ({ bundle }) => {
      _planId = bundle.plan_id;
      _request = bundle.request;
      _patches = bundle.patches || [];
      runValidation(_planId);
    });
  }

  function _reset() { _planId = null; _request = null; _report = null; _patches = []; }

  function _bindAccordion() {
    const header = document.getElementById('header-validation');
    const panel = document.getElementById('section-validation');
    if (header && panel) header.addEventListener('click', () => panel.classList.toggle('collapsed'));
  }

  function _expand() {
    const panel = document.getElementById('section-validation');
    if (panel) panel.classList.remove('collapsed');
  }

  // ---------------------------------------------------------------------------
  // Run validation
  // ---------------------------------------------------------------------------

  async function runValidation(planId) {
    planId = planId || _planId;
    if (!planId) return null;
    _planId = planId;
    _expand();
    _showLoading();
    try {
      _report = await API.validation.validate(planId);
      if (!_patches.length) {
        try { const b = await API.agent.result(planId); _patches = b.patches || []; _request = b.request; }
        catch { /* ignore */ }
      }
      _render();
      return _report;
    } catch (err) {
      _renderError(err.message);
      return null;
    }
  }

  async function approve() {
    if (!_planId) return null;
    const res = await API.validation.approve(_planId);
    if (_report) {
      _report.decision = res.decision;
      _report.next_phase = _report.next_phase || {};
      _report.next_phase.ready_to_apply = !!res.ready_to_apply;
    }
    _render();
    EventBus.emit('source:approval', { planId: _planId, ready: !!res.ready_to_apply, request: _request });
    return res;
  }

  async function reject() {
    if (!_planId) return null;
    const res = await API.validation.reject(_planId);
    if (_report) _report.decision = res.decision;
    _render();
    EventBus.emit('source:approval', { planId: _planId, ready: false, request: _request });
    return res;
  }

  async function regenerate() {
    if (!_request) return null;
    EventBus.emit('agent:trigger', { request: _request });
    const bundle = await API.agent.develop(_request);
    EventBus.emit('agent:result', { bundle }); // re-renders plan + re-validates
    return bundle;
  }

  function getPlanId() { return _planId; }
  function getReport() { return _report; }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  function _clearUI() {
    const c = document.getElementById('validation-panel-content');
    if (c) c.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No changes to validate yet</div>`;
  }

  function _showLoading() {
    const c = document.getElementById('validation-panel-content');
    if (!c) return;
    c.innerHTML = `
      <div class="analysis-progress-wrapper" style="background:rgba(59,130,246,0.05); border:1px solid rgba(59,130,246,0.15)">
        <div class="progress-label" style="color:#60a5fa"><span>Validating changes…</span></div>
        <div class="progress-track"><div class="progress-bar" style="width:60%; background:linear-gradient(90deg,#3b82f6,#2563eb)"></div></div>
        <div class="progress-status-text">Syntax · static · dependencies · tests · impact · risk</div>
      </div>`;
  }

  function _renderError(msg) {
    const c = document.getElementById('validation-panel-content');
    if (c) c.innerHTML = `<div style="color:var(--color-error); padding:5px 0;">Validation failed: ${Helpers.escapeHtml(msg || '')}</div>`;
  }

  function _render() {
    const c = document.getElementById('validation-panel-content');
    if (!c || !_report) return;
    const esc = Helpers.escapeHtml;
    const r = _report;
    const passed = r.validation_status === 'PASSED';
    const statusPill = `<span class="val-status-pill ${passed ? 'pass' : 'fail'}">${passed ? '✓ PASSED' : '✗ FAILED'}</span>`;
    const risk = r.risk || { level: 'Low' };
    const riskPill = `<span class="risk-badge ${esc((risk.level || 'low').toLowerCase())}">● ${esc(risk.level)} Risk</span>`;
    const decision = r.decision || { state: 'pending' };

    c.innerHTML = `
      <div class="val-card">
        <div class="val-card-row">${statusPill}${riskPill}</div>
        <div class="val-request" title="${esc(r.request)}">${esc(r.request)}</div>
      </div>

      <div class="agent-group-header"><span>Validation Stages</span></div>
      <div class="val-stages">${_stageRows(r.stages)}</div>

      ${_listBlock('Errors', r.summary.errors, 'err')}
      ${_listBlock('Warnings', r.summary.warnings, 'warn')}

      <div class="agent-group-header"><span>Tests</span></div>
      <div class="val-tests ${_testClass(r.stages.tests.status)}">${_testSummary(r.stages.tests)}</div>

      <div class="agent-group-header"><span>Final Diff</span></div>
      <div class="val-diff-list">${_diffRows(_patches)}</div>

      <div class="agent-group-header"><span>Approval</span></div>
      <div class="val-approval">
        <div class="val-decision ${esc(decision.state)}">Decision: <strong>${esc(decision.state)}</strong></div>
        <div class="val-approval-actions">
          <button class="btn val-approve" id="val-btn-approve" ${passed ? '' : 'disabled title="Resolve errors before approving"'}>Approve</button>
          <button class="btn val-reject" id="val-btn-reject">Reject</button>
          <button class="btn btn-ghost val-regen" id="val-btn-regen">Regenerate</button>
        </div>
        ${decision.state === 'approved'
          ? `<div class="val-note ok">Approved — ${r.next_phase.ready_to_apply ? 'ready for Phase 7 (apply).' : 'but validation has issues.'} No files modified.</div>`
          : decision.state === 'rejected'
            ? `<div class="val-note bad">Rejected — proposal discarded. No files modified.</div>`
            : `<div class="val-note">Awaiting your decision. No files modified.</div>`}
      </div>
    `;

    document.getElementById('val-btn-approve')?.addEventListener('click', () => { if (passed) approve(); });
    document.getElementById('val-btn-reject')?.addEventListener('click', reject);
    document.getElementById('val-btn-regen')?.addEventListener('click', regenerate);
    c.querySelectorAll('.val-diff-row[data-path]').forEach(row => {
      row.addEventListener('click', () => {
        const p = _patches.find(x => x.path === row.dataset.path);
        if (p && typeof Agent !== 'undefined') Agent.openDiff(p);
      });
    });
  }

  function _stageRows(stages) {
    const esc = Helpers.escapeHtml;
    const order = [['syntax', 'Syntax'], ['static', 'Static Analysis'], ['dependency', 'Dependencies'], ['tests', 'Tests'], ['impact', 'Change Impact']];
    return order.map(([key, label]) => {
      const s = stages[key] || {};
      let status = s.status || (key === 'tests' ? 'SKIPPED' : 'PASSED');
      const cls = { PASSED: 'pass', WARN: 'warn', FAILED: 'fail', SKIPPED: 'skip', TIMEOUT: 'warn' }[status] || 'skip';
      const counts = key === 'tests'
        ? ''
        : `<span class="val-stage-counts">✓${s.passed || 0} ⚠${s.warnings || 0} ✗${s.failed || 0}</span>`;
      return `
        <div class="val-stage-row">
          <span class="val-stage-dot ${cls}"></span>
          <span class="val-stage-name">${esc(label)}</span>
          <span class="val-stage-status ${cls}">${esc(status)}</span>
          ${counts}
        </div>`;
    }).join('');
  }

  function _listBlock(title, items, kind) {
    items = items || [];
    if (!items.length) return '';
    const esc = Helpers.escapeHtml;
    const rows = items.slice(0, 12).map(t => `<li class="val-li ${kind}">${esc(t)}</li>`).join('');
    const more = items.length > 12 ? `<li class="val-li ${kind}">…and ${items.length - 12} more</li>` : '';
    return `
      <div class="agent-group-header"><span>${esc(title)}</span><span class="impact-group-count">${items.length}</span></div>
      <ul class="val-list">${rows}${more}</ul>`;
  }

  function _testClass(status) {
    return { PASSED: 'pass', FAILED: 'fail', SKIPPED: 'skip', TIMEOUT: 'warn' }[status] || 'skip';
  }

  function _testSummary(t) {
    const esc = Helpers.escapeHtml;
    if (t.status === 'SKIPPED') return `<span>No runnable tests detected — skipped.</span>`;
    if (t.status === 'TIMEOUT') return `<span>Test run timed out.</span>`;
    return `<span><strong>${esc(t.status)}</strong> · ${t.passed || 0} passed, ${t.failed || 0} failed (${esc(t.framework || '—')})</span>`;
  }

  function _diffRows(patches) {
    if (!patches || !patches.length) return `<div style="font-style:italic; color:var(--color-text-muted); font-size:10px; padding:4px;">No diffs</div>`;
    const esc = Helpers.escapeHtml;
    return patches.map(p => `
      <div class="val-diff-row" data-path="${esc(p.path)}" title="View diff: ${esc(p.path)}">
        <span class="diff-change-badge ${esc(p.change_type)}">${esc(p.change_type)}</span>
        <span class="val-diff-name">${esc(p.path.split('/').pop())}</span>
        <span class="agent-change-stat"><span class="add">+${p.additions}</span> <span class="del">−${p.removals}</span></span>
      </div>`).join('');
  }

  return { init, runValidation, approve, reject, regenerate, getPlanId, getReport };
})();

window.Validation = Validation;
