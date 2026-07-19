/**
 * migration_validation.js — UI Module for Migration Validation & Approval (Phase 4).
 *
 * Validates the Phase 3 generated output and drives the approval workflow whose
 * result Phase 5 (Apply Migration) will consume. Read-only over the generated
 * code; it never applies, compiles, or modifies the original project.
 *
 *   - Runs /api/migration/validate and polls /validate/status.
 *   - Renders the validation dashboard (score ring, passed/failed/warnings/risk).
 *   - Renders the File Validation Table (file, status, issues, risk, actions).
 *   - Renders the Code Issue Viewer (errors, missing deps, recommendations, code).
 *   - Approve / Reject per file, Approve All Safe, Reject Migration.
 */

const MigrationValidation = (() => {
  let _pollInterval = null;
  let _report = null;
  let _activeFilter = 'all';
  let _selectedPath = null;

  const VALIDATION_STEPS = [
    "Loading Generated Files",
    "Syntax Validation",
    "Dependency Validation",
    "Architecture Validation",
    "Configuration Validation",
    "Consistency Validation",
    "Risk Analysis",
    "Building Validation Report",
    "Validation Completed"
  ];

  const RING_CIRC = 2 * Math.PI * 52;  // r=52

  // ---------------------------------------------------------------------------
  // Init & bindings
  // ---------------------------------------------------------------------------

  function init() {
    document.getElementById('btn-run-validation')?.addEventListener('click', runValidation);
    document.getElementById('btn-approve-safe')?.addEventListener('click', _approveAllSafe);
    document.getElementById('btn-reject-migration')?.addEventListener('click', _rejectMigration);

    document.getElementById('validation-filters')?.addEventListener('click', (e) => {
      const chip = e.target.closest('.migration-gen-filter');
      if (!chip) return;
      _activeFilter = chip.dataset.filter || 'all';
      document.querySelectorAll('#validation-filters .migration-gen-filter').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      _renderTable();
    });

    EventBus.on('project:closed', reset);
  }

  // Called by MigrationAgent when Phase 3 generation completes.
  function onGenerationComplete() {
    const section = document.getElementById('migration-validation-section');
    if (section) section.style.display = 'block';
    const btn = document.getElementById('btn-run-validation');
    if (btn) { btn.disabled = false; btn.textContent = 'Validate Migration'; }
    _setValidateHint('Generation complete — click “Validate Migration” to check the generated code.');
  }

  function reset() {
    _stopPolling();
    _report = null;
    _activeFilter = 'all';
    _selectedPath = null;
    const section = document.getElementById('migration-validation-section');
    if (section) section.style.display = 'none';
    const dash = document.getElementById('validation-dashboard');
    if (dash) dash.style.display = 'none';
    const grid = document.getElementById('validation-results-grid');
    if (grid) grid.style.display = 'none';
    // Best-effort backend reset (ignore failures).
    if (typeof API !== 'undefined') API.migration.resetValidation?.().catch(() => {});
    // Cascade: tear down Phase 5 apply UI too.
    if (typeof MigrationApply !== 'undefined') MigrationApply.reset();
  }

  // ---------------------------------------------------------------------------
  // Run validation
  // ---------------------------------------------------------------------------

  async function runValidation() {
    _stopPolling();
    const btn = document.getElementById('btn-run-validation');
    if (btn) { btn.disabled = true; btn.textContent = 'Validating…'; }
    _setValidateHint('Running validation…');
    _resetProgress();
    _renderSteps({ step_logs: [], current_step: 'Loading Generated Files', status: 'validating' });

    try {
      await API.migration.validate();
      _startPolling();
    } catch (err) {
      if (btn) { btn.disabled = false; btn.textContent = 'Validate Migration'; }
      Toast.show(`Validation failed to start: ${err.message}`, 'error');
    }
  }

  function _startPolling() {
    _stopPolling();
    _poll();
    _pollInterval = setInterval(_poll, 400);
  }
  function _stopPolling() {
    if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
  }

  async function _poll() {
    try {
      const data = await API.migration.validateStatus();
      const bar = document.getElementById('validation-progress-bar');
      if (bar) bar.style.width = `${Math.max(data.progress || 0, 4)}%`;
      _renderSteps(data);

      if (data.status === 'completed') {
        _stopPolling();
        _report = data.report;
        _onComplete();
      } else if (data.status === 'failed') {
        _stopPolling();
        const btn = document.getElementById('btn-run-validation');
        if (btn) { btn.disabled = false; btn.textContent = 'Validate Migration'; }
        _setValidateHint(`Validation error: ${data.error || 'unknown'}`, true);
        Toast.show(`Validation error: ${data.error || 'unknown'}`, 'error');
      }
    } catch (err) {
      console.warn('[MigrationValidation] poll failed:', err);
    }
  }

  function _onComplete() {
    const btn = document.getElementById('btn-run-validation');
    if (btn) { btn.disabled = false; btn.textContent = 'Re-run Validation'; }
    document.getElementById('validation-dashboard').style.display = 'block';
    document.getElementById('validation-results-grid').style.display = 'grid';
    _renderDashboard(_report);
    _renderTable();
    _refreshApprovalBadge();
    // Auto-open the first file's issue viewer.
    if (_report.files && _report.files.length) _selectFile(_report.files[0].generated_path);
    Toast.show(`Validation complete — score ${_report.validation_score}%`, 'success');

    // Phase 5: reveal the application workspace (change preview + history).
    if (typeof MigrationApply !== 'undefined') MigrationApply.onValidationComplete();
  }

  // ---------------------------------------------------------------------------
  // Progress checklist
  // ---------------------------------------------------------------------------

  function _renderSteps(data) {
    const el = document.getElementById('validation-steps-log');
    if (!el) return;
    const logs = data.step_logs || [];
    const logged = new Set(logs.map(l => l.step));
    const current = data.current_step;
    const done = data.status === 'completed';
    const failed = data.status === 'failed';

    el.innerHTML = '';
    VALIDATION_STEPS.forEach(name => {
      let cls = 'waiting';
      if (done) cls = logged.has(name) ? 'completed' : 'waiting';
      else if (name === current) cls = failed ? 'error' : 'running';
      else if (logged.has(name)) cls = 'completed';
      const last = [...logs].reverse().find(l => l.step === name);
      const row = document.createElement('div');
      row.className = `migration-step-row${cls === 'running' ? ' active' : ''}`;
      row.innerHTML = `<span class="migration-step-dot ${cls}"></span>
        <span class="migration-step-text">${Helpers.escapeHtml(name)}</span>
        <span class="migration-step-time">${last ? (last.timestamp || '') : ''}</span>`;
      el.appendChild(row);
    });
  }

  // ---------------------------------------------------------------------------
  // Dashboard (score ring + stat cards)
  // ---------------------------------------------------------------------------

  function _renderDashboard(r) {
    const s = r.summary || {};
    const score = r.validation_score || 0;

    // Score ring
    const ring = document.getElementById('validation-score-ring-fill');
    if (ring) {
      const offset = RING_CIRC * (1 - score / 100);
      ring.style.strokeDasharray = `${RING_CIRC}`;
      ring.style.strokeDashoffset = `${offset}`;
      ring.style.stroke = score >= 80 ? 'var(--color-success)'
        : score >= 50 ? 'var(--color-warning)' : 'var(--color-error)';
    }
    _setText('validation-score-text', `${score}%`);
    _setText('validation-success-text', `${r.success_percentage || 0}% success`);

    _setText('val-stat-passed', s.passed || 0);
    _setText('val-stat-warnings', s.warnings || 0);
    _setText('val-stat-failed', s.failed || 0);
    _setText('val-stat-review', s.manual_review || 0);
    const riskEl = document.getElementById('val-stat-risk');
    if (riskEl) {
      riskEl.textContent = r.risk_level || 'Unknown';
      riskEl.className = 'migration-stat-value ' + _riskClass(r.risk_level);
    }

    // Filter counts
    _setChipCount('all', s.total_files);
    _setChipCount('passed', s.passed);
    _setChipCount('warning', s.warnings);
    _setChipCount('manual_review', s.manual_review);
    _setChipCount('failed', s.failed);
  }

  function _riskClass(level) {
    const l = (level || '').toLowerCase();
    if (l.startsWith('high')) return 'error';
    if (l.startsWith('medium')) return 'warning';
    if (l.startsWith('low')) return 'success';
    return '';
  }

  // ---------------------------------------------------------------------------
  // File Validation Table
  // ---------------------------------------------------------------------------

  function _filteredFiles() {
    const files = (_report && _report.files) || [];
    if (_activeFilter === 'all') return files;
    return files.filter(f => f.validation_status === _activeFilter);
  }

  function _renderTable() {
    const tbody = document.getElementById('validation-table-body');
    if (!tbody) return;
    const files = _filteredFiles();
    if (!files.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="migration-gen-empty">No files for this filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = '';
    files.forEach(f => {
      const tr = document.createElement('tr');
      tr.className = 'validation-row' + (f.generated_path === _selectedPath ? ' selected' : '');
      tr.dataset.path = f.generated_path;
      const name = f.generated_path.split('/').pop();
      const approveDisabled = !f.auto_approvable ? 'disabled' : '';
      const approveTitle = !f.auto_approvable
        ? 'Failed / manual-review files cannot be approved' : 'Approve file';

      tr.innerHTML = `
        <td class="v-file" title="${Helpers.escapeHtml(f.generated_path)}">
          <span class="v-file-name">${Helpers.escapeHtml(name)}</span>
          <span class="v-file-comp">${Helpers.escapeHtml(f.component_type)}</span>
        </td>
        <td><span class="v-status ${f.validation_status}">${_statusLabel(f.validation_status)}</span></td>
        <td class="v-issues">${f.issues.length || '—'}</td>
        <td><span class="v-risk ${f.risk}">${_riskLabel(f.risk)}</span></td>
        <td class="v-actions">
          <span class="v-approval ${f.approval}">${_approvalLabel(f.approval)}</span>
          <button class="v-btn v-approve" data-act="approve" ${approveDisabled} title="${approveTitle}">✓</button>
          <button class="v-btn v-reject" data-act="reject" title="Reject file">✗</button>
        </td>`;

      tr.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-act]');
        if (btn) {
          e.stopPropagation();
          if (btn.hasAttribute('disabled')) return;
          if (btn.dataset.act === 'approve') _approveFile(f.generated_path);
          else _rejectFile(f.generated_path);
          return;
        }
        _selectFile(f.generated_path);
      });
      tbody.appendChild(tr);
    });
  }

  function _statusLabel(s) {
    return { passed: '✓ Passed', warning: '⚠ Warning', failed: '✗ Failed', manual_review: '🔍 Review' }[s] || s;
  }
  function _riskLabel(r) {
    return { safe: 'Safe', warning: 'Warning', high_risk: 'High Risk', manual_review: 'Manual Review' }[r] || r;
  }
  function _approvalLabel(a) {
    return { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' }[a] || a;
  }

  // ---------------------------------------------------------------------------
  // Code Issue Viewer
  // ---------------------------------------------------------------------------

  async function _selectFile(path) {
    _selectedPath = path;
    _renderTable();
    const body = document.getElementById('validation-issue-body');
    const title = document.getElementById('validation-issue-title');
    if (title) title.textContent = path;
    if (body) body.innerHTML = '<div class="migration-diff-empty">Loading…</div>';
    try {
      const res = await API.migration.validateFile(path);
      _renderIssueViewer(res);
    } catch (err) {
      if (body) body.innerHTML = `<div class="migration-diff-empty error">Failed to load: ${Helpers.escapeHtml(err.message)}</div>`;
    }
  }

  function _renderIssueViewer(res) {
    const body = document.getElementById('validation-issue-body');
    if (!body) return;
    const r = res.result;
    const errLines = new Set(r.issues.filter(i => i.line).map(i => i.line));

    const issuesHtml = r.issues.length ? r.issues.map(i => `
      <div class="v-issue ${i.severity}">
        <span class="v-issue-cat">${Helpers.escapeHtml(i.category)}</span>
        <span class="v-issue-msg">${Helpers.escapeHtml(i.message)}${i.line ? ` <em>(line ${i.line})</em>` : ''}</span>
        ${i.detail ? `<div class="v-issue-detail">${Helpers.escapeHtml(i.detail)}</div>` : ''}
      </div>`).join('') : '<div class="v-none">No issues found for this file.</div>';

    const depsHtml = r.missing_dependencies.length
      ? `<div class="v-block"><div class="v-block-h">Missing Dependencies</div>${
          r.missing_dependencies.map(d => `<code class="v-dep">${Helpers.escapeHtml(d)}</code>`).join(' ')}</div>`
      : '';

    const recsHtml = r.recommendations.length
      ? `<div class="v-block"><div class="v-block-h">Recommendations</div>${
          r.recommendations.map(x => `<div class="v-rec">• ${Helpers.escapeHtml(x)}</div>`).join('')}</div>`
      : '';

    const code = (res.generated_content || '').split('\n').map((ln, idx) => {
      const n = idx + 1;
      const cls = errLines.has(n) ? ' err' : '';
      return `<div class="v-code-line${cls}"><span class="ln">${n}</span><span class="code">${Helpers.escapeHtml(ln)}</span></div>`;
    }).join('');

    const approveDisabled = !r.auto_approvable ? 'disabled' : '';
    body.innerHTML = `
      <div class="v-issue-head">
        <span class="v-status ${r.validation_status}">${_statusLabel(r.validation_status)}</span>
        <span class="v-risk ${r.risk}">${_riskLabel(r.risk)}</span>
        <span class="v-approval ${r.approval}">${_approvalLabel(r.approval)}</span>
        <span class="v-score">score ${r.score}</span>
        <span class="v-viewer-actions">
          <button class="btn btn-ghost v-vbtn" id="v-viewer-approve" ${approveDisabled}>Approve</button>
          <button class="btn btn-ghost v-vbtn" id="v-viewer-reject">Reject</button>
        </span>
      </div>
      <div class="v-block"><div class="v-block-h">Validation Issues (${r.issues.length})</div>${issuesHtml}</div>
      ${depsHtml}
      ${recsHtml}
      <div class="v-block"><div class="v-block-h">Generated Code (read-only)</div>
        <div class="v-code">${code}</div>
      </div>`;

    document.getElementById('v-viewer-approve')?.addEventListener('click', () => {
      if (!r.auto_approvable) return;
      _approveFile(r.generated_path);
    });
    document.getElementById('v-viewer-reject')?.addEventListener('click', () => _rejectFile(r.generated_path));
  }

  // ---------------------------------------------------------------------------
  // Approval workflow
  // ---------------------------------------------------------------------------

  async function _approveFile(path) {
    try {
      const res = await API.migration.approveFile(path);
      if (!res.success) { Toast.show(res.message || 'Cannot approve this file.', 'warning'); return; }
      Toast.show(`Approved ${path.split('/').pop()}`, 'success', 1500);
      await _refreshAfterApproval();
    } catch (err) { Toast.show(`Approve failed: ${err.message}`, 'error'); }
  }

  async function _rejectFile(path) {
    try {
      await API.migration.rejectFile(path);
      Toast.show(`Rejected ${path.split('/').pop()}`, 'info', 1500);
      await _refreshAfterApproval();
    } catch (err) { Toast.show(`Reject failed: ${err.message}`, 'error'); }
  }

  async function _approveAllSafe() {
    try {
      const res = await API.migration.approveAllSafe();
      Toast.show(`Approved ${res.approved} safe file(s)`, 'success');
      await _refreshAfterApproval();
    } catch (err) { Toast.show(`Approve all failed: ${err.message}`, 'error'); }
  }

  async function _rejectMigration() {
    const ok = await Helpers.confirmModal({
      title: 'Reject Migration',
      message: 'Reject ALL generated files? This marks the entire migration as rejected (nothing is deleted).',
      confirmText: 'Reject All', danger: true,
    });
    if (!ok) return;
    try {
      const res = await API.migration.rejectMigration();
      Toast.show(`Rejected ${res.rejected} file(s)`, 'info');
      await _refreshAfterApproval();
    } catch (err) { Toast.show(`Reject migration failed: ${err.message}`, 'error'); }
  }

  async function _refreshAfterApproval() {
    // Re-pull status so approval states + report are fresh, then re-render.
    try {
      const data = await API.migration.validateStatus();
      if (data.report) _report = data.report;
      _renderTable();
      if (_selectedPath) _selectFile(_selectedPath);
      _refreshApprovalBadge();
      // Approval state changed → refresh the Phase 5 change preview.
      if (typeof MigrationApply !== 'undefined') MigrationApply.loadChanges();
    } catch (_) { /* ignore */ }
  }

  async function _refreshApprovalBadge() {
    try {
      const out = await API.migration.approvalOutput();
      const badge = document.getElementById('validation-ready-badge');
      if (badge) {
        badge.textContent = `Approved ${out.approved_files.length} · Rejected ${out.rejected_files.length} · Pending ${out.pending_review_files.length}`
          + (out.ready_for_apply ? ' · Ready for Phase 5 ✓' : '');
        badge.className = 'validation-ready-badge' + (out.ready_for_apply ? ' ready' : '');
      }
    } catch (_) { /* ignore */ }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function _setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
  function _setChipCount(filter, v) {
    const el = document.querySelector(`#validation-filters .migration-gen-filter[data-filter="${filter}"] .count`);
    if (el) el.textContent = (v === undefined || v === null) ? '0' : v;
  }
  function _setValidateHint(text, isError) {
    const el = document.getElementById('validation-hint');
    if (el) { el.textContent = text; el.style.color = isError ? 'var(--color-error)' : ''; }
  }
  function _resetProgress() {
    const bar = document.getElementById('validation-progress-bar');
    if (bar) bar.style.width = '4%';
  }

  return { init, onGenerationComplete, reset };
})();
