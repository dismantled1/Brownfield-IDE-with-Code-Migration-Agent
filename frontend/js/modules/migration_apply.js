/**
 * migration_apply.js — UI Module for the Migration Application Engine (Phase 5).
 *
 * Applies APPROVED migrated code into the project (with backups + rollback) and
 * shows the change preview, success screen, and migration history. Consumes prior
 * phase output only — it never regenerates, re-analyzes, or re-validates.
 *
 *   - Preview change set (/api/migration/changes) with per-file old→new diff.
 *   - Apply approved migration (/api/migration/apply) → success screen + report.
 *   - Migration history (/api/migration/history) with per-migration rollback.
 *   - Rollback (/api/migration/rollback), then auto-refresh the IDE (Explorer).
 */

const MigrationApply = (() => {
  let _changeSet = null;
  let _lastReport = null;
  let _selectedPath = null;

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    document.getElementById('btn-preview-changes')?.addEventListener('click', loadChanges);
    document.getElementById('btn-apply-migration')?.addEventListener('click', applyMigration);
    document.getElementById('btn-open-project')?.addEventListener('click', _openProject);
    document.getElementById('btn-view-report')?.addEventListener('click', _toggleReport);
    document.getElementById('btn-rollback-last')?.addEventListener('click', () => {
      if (_lastReport) _rollback(_lastReport.migration_id);
    });
    EventBus.on('project:closed', reset);
  }

  // Called by MigrationValidation when validation completes.
  function onValidationComplete() {
    const section = document.getElementById('migration-apply-section');
    if (section) section.style.display = 'block';
    loadChanges();
    loadHistory();
  }

  function reset() {
    _changeSet = null; _lastReport = null; _selectedPath = null;
    const section = document.getElementById('migration-apply-section');
    if (section) section.style.display = 'none';
    const succ = document.getElementById('apply-success-card');
    if (succ) succ.style.display = 'none';
  }

  // ---------------------------------------------------------------------------
  // Change set preview
  // ---------------------------------------------------------------------------

  async function loadChanges() {
    const list = document.getElementById('apply-change-list');
    const summary = document.getElementById('apply-change-summary');
    const applyBtn = document.getElementById('btn-apply-migration');
    if (list) list.innerHTML = '<div class="migration-gen-empty">Loading changes…</div>';

    try {
      _changeSet = await API.migration.changes();
    } catch (err) {
      if (list) list.innerHTML = `<div class="migration-diff-empty error">${Helpers.escapeHtml(err.message)}</div>`;
      return;
    }

    const cs = _changeSet;
    const total = cs.to_create.length + cs.to_replace.length + cs.to_modify.length + cs.to_delete.length + cs.to_rename.length;

    if (summary) {
      summary.innerHTML = `
        <span class="apply-chip create">Create ${cs.to_create.length}</span>
        <span class="apply-chip replace">Replace ${cs.to_replace.length}</span>
        <span class="apply-chip modify">Modify ${cs.to_modify.length}</span>
        <span class="apply-chip delete">Delete ${cs.to_delete.length}</span>
        <span class="apply-chip skip">Skipped ${cs.skipped.length}</span>`;
    }

    if (applyBtn) applyBtn.disabled = !cs.ready;
    _setHint(cs.ready ? `${total} approved file(s) ready to apply.` : (cs.message || 'Nothing to apply.'));

    if (list) {
      if (!total) {
        list.innerHTML = `<div class="migration-gen-empty">${Helpers.escapeHtml(cs.message || 'No approved files to apply.')}</div>`;
      } else {
        list.innerHTML = '';
        _appendGroup(list, 'Create', cs.to_create, 'create');
        _appendGroup(list, 'Replace', cs.to_replace, 'replace');
        _appendGroup(list, 'Modify', cs.to_modify, 'modify');
        _appendGroup(list, 'Delete', cs.to_delete, 'delete');
        _appendGroup(list, 'Rename', cs.to_rename, 'rename');
      }
    }
  }

  function _appendGroup(container, label, items, cls) {
    if (!items.length) return;
    const head = document.createElement('div');
    head.className = 'apply-group-head';
    head.textContent = `${label} (${items.length})`;
    container.appendChild(head);
    items.forEach(it => {
      const row = document.createElement('div');
      row.className = 'apply-change-row' + (it.target_path === _selectedPath ? ' selected' : '');
      row.innerHTML = `
        <span class="apply-mode ${cls}">${label[0]}</span>
        <span class="apply-change-name" title="${Helpers.escapeHtml(it.target_path)}">${Helpers.escapeHtml(it.target_path)}</span>
        <span class="migration-gen-counts"><span class="add">+${it.additions || 0}</span> <span class="rem">-${it.removals || 0}</span></span>`;
      row.addEventListener('click', () => _previewDiff(it.generated_path, it.target_path));
      container.appendChild(row);
    });
  }

  // ---------------------------------------------------------------------------
  // Diff preview (reuses the Phase 3 generated-file endpoint: original → generated)
  // ---------------------------------------------------------------------------

  async function _previewDiff(generatedPath, targetPath) {
    _selectedPath = targetPath;
    const title = document.getElementById('apply-diff-title');
    const body = document.getElementById('apply-diff-body');
    if (title) title.textContent = targetPath;
    if (body) body.innerHTML = '<div class="migration-diff-empty">Loading…</div>';
    try {
      const res = await API.migration.generatedFile(generatedPath);
      const rows = res.file.diff_rows || [];
      if (!rows.length) { body.innerHTML = '<div class="migration-diff-empty">No differences.</div>'; return; }
      let html = '';
      rows.forEach(r => {
        if (r.type === 'equal') html += _line(r.left_num, ' ', r.left, 'equal');
        else if (r.type === 'remove') html += _line(r.left_num, '-', r.left, 'remove');
        else if (r.type === 'add') html += _line(r.right_num, '+', r.right, 'add');
        else if (r.type === 'modify') { html += _line(r.left_num, '-', r.left, 'remove'); html += _line(r.right_num, '+', r.right, 'add'); }
      });
      body.innerHTML = `<div class="migration-diff-unified">${html}</div>`;
    } catch (err) {
      body.innerHTML = `<div class="migration-diff-empty error">${Helpers.escapeHtml(err.message)}</div>`;
    }
    loadChanges();  // refresh selection highlight
  }

  function _line(num, sign, text, cls) {
    return `<div class="migration-code-line ${cls}"><span class="ln">${num || ''}</span>` +
      `<span class="sign">${sign}</span><span class="code">${Helpers.escapeHtml(text || '')}</span></div>`;
  }

  // ---------------------------------------------------------------------------
  // Apply
  // ---------------------------------------------------------------------------

  async function applyMigration() {
    if (!_changeSet || !_changeSet.ready) { Toast.show('Nothing approved to apply.', 'warning'); return; }
    const total = _changeSet.to_create.length + _changeSet.to_replace.length + _changeSet.to_modify.length + _changeSet.to_delete.length;
    const ok = await Helpers.confirmModal({
      title: 'Apply Migration',
      message: `Apply ${total} approved file(s) to the project? Originals are backed up first and this can be rolled back.`,
      confirmText: 'Apply Migration',
    });
    if (!ok) return;

    const btn = document.getElementById('btn-apply-migration');
    if (btn) { btn.disabled = true; btn.textContent = 'Applying…'; }
    try {
      const report = await API.migration.apply();
      _lastReport = report;
      _showSuccess(report);
      Toast.show('Migration applied ✓', 'success');
      EventBus.emit('explorer:refresh');   // refresh Project Explorer
      loadHistory();
      loadChanges();
    } catch (err) {
      Toast.show(`Apply failed: ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Apply Migration'; }
    }
  }

  function _showSuccess(report) {
    const card = document.getElementById('apply-success-card');
    const stats = document.getElementById('apply-success-stats');
    if (card) card.style.display = 'flex';
    if (stats) {
      const s = report.summary || {};
      stats.innerHTML = `
        <div class="apply-stat"><span class="v">${report.new_files.length}</span><span class="l">Files Created</span></div>
        <div class="apply-stat"><span class="v">${report.modified_files.length}</span><span class="l">Files Updated</span></div>
        <div class="apply-stat"><span class="v">${report.deleted_files.length}</span><span class="l">Files Deleted</span></div>
        <div class="apply-stat"><span class="v">${report.skipped_files.length}</span><span class="l">Files Skipped</span></div>
        <div class="apply-stat"><span class="v ok">✓</span><span class="l">Rollback Available</span></div>`;
    }
    const rv = document.getElementById('apply-report-viewer');
    if (rv) { rv.style.display = 'none'; rv.textContent = report.report_markdown || ''; }
    if (card) card.scrollIntoView({ block: 'start' });
  }

  function _toggleReport() {
    const rv = document.getElementById('apply-report-viewer');
    if (!rv) return;
    rv.style.display = rv.style.display === 'none' ? 'block' : 'none';
  }

  function _openProject() {
    EventBus.emit('explorer:refresh');
    if (typeof Migration !== 'undefined') Migration.closeWorkspace();
  }

  // ---------------------------------------------------------------------------
  // History + rollback
  // ---------------------------------------------------------------------------

  async function loadHistory() {
    const tbody = document.getElementById('apply-history-body');
    if (!tbody) return;
    try {
      const res = await API.migration.history();
      const hist = res.history || [];
      if (!hist.length) { tbody.innerHTML = '<tr><td colspan="7" class="migration-gen-empty">No migrations applied yet.</td></tr>'; return; }
      tbody.innerHTML = '';
      hist.forEach(m => {
        const tr = document.createElement('tr');
        tr.className = 'validation-row';
        const date = (m.timestamp || '').replace('T', ' ').slice(0, 19);
        const canRollback = m.rollback_available && !m.rolled_back;
        tr.innerHTML = `
          <td><code>${Helpers.escapeHtml(m.migration_id)}</code></td>
          <td>${Helpers.escapeHtml(date)}</td>
          <td>${m.files_applied}</td>
          <td>${m.files_created}</td>
          <td>${m.files_deleted}</td>
          <td>${Helpers.escapeHtml(m.applied_by || '')}</td>
          <td>${canRollback
            ? `<button class="btn btn-ghost v-vbtn apply-rollback-btn" data-id="${m.migration_id}">Rollback</button>`
            : '<span class="v-approval rejected">Rolled back</span>'}</td>`;
        const btn = tr.querySelector('.apply-rollback-btn');
        if (btn) btn.addEventListener('click', () => _rollback(m.migration_id));
        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="migration-diff-empty error">${Helpers.escapeHtml(err.message)}</td></tr>`;
    }
  }

  async function _rollback(migrationId) {
    const ok = await Helpers.confirmModal({
      title: 'Rollback Migration',
      message: `Restore the project to its state before migration ${migrationId}? Created files are removed and originals are restored from backup.`,
      confirmText: 'Rollback', danger: true,
    });
    if (!ok) return;
    try {
      const res = await API.migration.rollback(migrationId);
      if (!res.success) { Toast.show(res.message || 'Rollback not available.', 'warning'); return; }
      Toast.show(res.message || 'Rolled back.', 'success');
      EventBus.emit('explorer:refresh');
      loadHistory();
      const succ = document.getElementById('apply-success-card');
      if (succ) succ.style.display = 'none';
    } catch (err) {
      Toast.show(`Rollback failed: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function _setHint(text) {
    const el = document.getElementById('apply-hint');
    if (el) el.textContent = text;
  }

  return { init, onValidationComplete, reset, loadHistory, loadChanges };
})();
