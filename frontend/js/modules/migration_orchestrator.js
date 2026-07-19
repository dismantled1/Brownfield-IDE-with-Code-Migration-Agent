/**
 * Migration Orchestrator Module — Phase 6: Final Integration & Console
 * ====================================================================
 * Connects the Migration Workspace to the backend MigrationOrchestrator.
 * Renders the Live Execution Console with timestamped streaming log entries,
 * populates the Unified Dashboard stats, and supports reopening historical reports.
 */

window.MigrationOrchestrator = (function () {
  let activePollInterval = null;
  let isRunning = false;

  function init() {
    bindEvents();
    fetchDashboard();
  }

  function bindEvents() {
    const startBtn = document.getElementById('migration-start-btn');
    if (startBtn) {
      startBtn.addEventListener('click', onStartWorkflow);
    }

    const cancelBtn = document.getElementById('migration-console-cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', onCancelWorkflow);
    }
  }

  async function fetchDashboard() {
    try {
      const resp = await API.migration.dashboard();
      if (resp) {
        renderDashboard(resp);
      }
    } catch (err) {
      console.warn('[MigrationOrchestrator] Dashboard fetch failed:', err);
    }
  }

  function renderDashboard(dash) {
    if (!dash) return;

    // AI Provider diagnostics badge
    const provBadge = document.getElementById('dash-provider-badge');
    if (provBadge) {
      provBadge.textContent = `${dash.current_provider.toUpperCase()} (${dash.current_model || 'default'})`;
      provBadge.className = `badge ${dash.ollama_installed ? 'badge-success' : 'badge-warning'}`;
    }

    // Platform stats
    const setElem = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val !== undefined && val !== null ? val : '—';
    };

    setElem('dash-project-name', dash.project_name || 'Brownfield IDE');
    setElem('dash-source-lang', dash.source_language || 'Auto');
    setElem('dash-target-lang', dash.target_language || 'Java');
    setElem('dash-framework', dash.framework || 'Detected');
    setElem('dash-scope', (dash.migration_scope || 'project').toUpperCase());
    setElem('dash-total-files', dash.total_files);
    setElem('dash-selected-files', dash.selected_files);
    setElem('dash-generated-files', dash.generated_files);
    setElem('dash-applied-files', dash.applied_files);
    setElem('dash-val-score', dash.validation_score ? `${dash.validation_score}/100` : '—');
    setElem('dash-risk-category', dash.risk_category || 'N/A');
    setElem('dash-rollback-status', dash.rollback_available ? 'AVAILABLE' : 'NONE');

    const progressFill = document.getElementById('dash-progress-fill');
    if (progressFill) {
      progressFill.style.width = `${dash.global_progress || 0}%`;
    }
  }

  async function onStartWorkflow(evt) {
    if (evt) evt.preventDefault();
    if (isRunning) return;

    const scopeRadios = document.getElementsByName('migration-scope');
    let scope = 'project';
    for (const r of scopeRadios) {
      if (r.checked) {
        scope = r.value;
        break;
      }
    }

    const sourceLang = document.getElementById('migration-source-lang')?.value || 'auto';
    const targetLang = document.getElementById('migration-target-lang')?.value || 'java';

    const stratBoxes = document.querySelectorAll('.migration-strategy-cb:checked');
    const strategies = Array.from(stratBoxes).map((cb) => cb.value);

    let targetPath = null;
    if (scope === 'file') {
      targetPath = (typeof TabBar !== 'undefined' ? TabBar.getActive() : null) || (typeof Editor !== 'undefined' ? Editor.getActiveFilePath() : null) || (typeof Explorer !== 'undefined' ? Explorer.getSelectedPath() : null);
    } else if (scope === 'folder') {
      targetPath = typeof Explorer !== 'undefined' ? Explorer.getSelectedFolder() : null;
    }

    if ((scope === 'file' || scope === 'folder') && !targetPath) {
      if (typeof Toast !== 'undefined') Toast.show('Please select a valid file or folder target to continue', 'warning');
      isRunning = false;
      return;
    }

    try {
      isRunning = true;
      toggleConsole(true);

      const resp = await API.migration.startWorkflow(scope, targetPath, sourceLang, targetLang, strategies, false);
      if (resp && resp.success) {
        startPolling();
      } else {
        appendLog('ERROR', 'Platform', 'Failed to launch workflow', 'error');
        isRunning = false;
      }
    } catch (err) {
      console.error('[MigrationOrchestrator] Start workflow error:', err);
      appendLog('ERROR', 'Platform', String(err), 'error');
      isRunning = false;
    }
  }

  async function onCancelWorkflow() {
    try {
      await API.migration.cancelWorkflow();
      appendLog('CANCELLED', 'Platform', 'Workflow cancelled by user', 'warning');
      stopPolling();
      isRunning = false;
    } catch (err) {
      console.warn('[MigrationOrchestrator] Cancel workflow error:', err);
    }
  }

  function startPolling() {
    stopPolling();
    pollStatus();
    activePollInterval = setInterval(pollStatus, 800);
  }

  function stopPolling() {
    if (activePollInterval) {
      clearInterval(activePollInterval);
      activePollInterval = null;
    }
  }

  async function pollStatus() {
    try {
      const status = await API.migration.workflowStatus();
      if (!status) return;

      renderLogStream(status.step_logs);
      renderDashboard(status.dashboard);

      const statusBadge = document.getElementById('migration-console-status-badge');
      if (statusBadge) {
        statusBadge.textContent = (status.state || 'running').toUpperCase();
        statusBadge.className = `badge badge-${status.state === 'completed' ? 'success' : status.state === 'failed' ? 'danger' : 'info'}`;
      }

      if (status.state === 'completed' || status.state === 'failed') {
        stopPolling();
        isRunning = false;
        if (status.state === 'completed') {
          // Reveal validation and apply modules automatically
          if (window.MigrationAgent && MigrationAgent.onWorkflowCompleted) {
            MigrationAgent.onWorkflowCompleted();
          }
        }
      }
    } catch (err) {
      console.warn('[MigrationOrchestrator] Poll status error:', err);
    }
  }

  function renderLogStream(logs) {
    const consoleContainer = document.getElementById('migration-console-log-stream');
    if (!consoleContainer || !Array.isArray(logs)) return;

    consoleContainer.innerHTML = '';
    logs.forEach((log) => {
      const line = document.createElement('div');
      line.className = `console-log-line log-${log.status || 'info'}`;
      
      const icon = log.status === 'success' ? '✓' : log.status === 'warning' ? '⚠' : log.status === 'error' ? '✗' : 'ℹ';
      line.innerHTML = `
        <span class="console-timestamp">[${log.timestamp}]</span>
        <span class="console-phase">[${log.phase}]</span>
        <span class="console-icon">${icon}</span>
        <span class="console-message">${escapeHtml(log.message)}</span>
        ${log.duration_s ? `<span class="console-duration">(${log.duration_s}s)</span>` : ''}
      `;
      consoleContainer.appendChild(line);
    });

    consoleContainer.scrollTop = consoleContainer.scrollHeight;
  }

  function appendLog(timestamp, phase, message, status = 'info') {
    const consoleContainer = document.getElementById('migration-console-log-stream');
    if (!consoleContainer) return;

    const line = document.createElement('div');
    line.className = `console-log-line log-${status}`;
    line.innerHTML = `
      <span class="console-timestamp">[${timestamp}]</span>
      <span class="console-phase">[${phase}]</span>
      <span class="console-message">${escapeHtml(message)}</span>
    `;
    consoleContainer.appendChild(line);
    consoleContainer.scrollTop = consoleContainer.scrollHeight;
  }

  function toggleConsole(show) {
    const consoleBox = document.getElementById('migration-live-console');
    if (consoleBox) {
      consoleBox.style.display = show ? 'block' : 'none';
    }
  }

  async function reopenHistoricalReport(migrationId) {
    try {
      const report = await API.migration.archivedReport(migrationId);
      if (!report) return;

      // Render historical report markdown into report viewer
      const reportViewer = document.getElementById('migration-report-viewer');
      if (reportViewer) {
        const mdContent = report.plan_markdown || report.apply_markdown || report.validation_markdown;
        reportViewer.innerHTML = window.marked ? marked.parse(mdContent) : `<pre>${escapeHtml(mdContent)}</pre>`;
      }
      
      // Toast notification
      if (window.showToast) {
        showToast(`Loaded historical migration report #${migrationId}`, 'info');
      }
    } catch (err) {
      console.error('[MigrationOrchestrator] Error loading historical report:', err);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return {
    init,
    fetchDashboard,
    onStartWorkflow,
    onCancelWorkflow,
    reopenHistoricalReport,
  };
})();
