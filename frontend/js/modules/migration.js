/**
 * migration.js — UI Module for the AI Code Migration Agent (Phase 2).
 * Connects frontend workspace UI to backend Migration Analysis Engine.
 * Manages configuration controls, real-time progress polling, summary counters,
 * and Markdown migration plan report rendering.
 */

const Migration = (() => {
  let _isOpen = false;
  let _pollInterval = null;
  let _lastConfig = null;  // config chosen at Start (handed to Phase 3 generation)

  // Standard steps list for progress panel rendering
  const ANALYSIS_STEPS = [
    "Project Loaded",
    "Detecting Source Language",
    "Detecting Framework",
    "Analyzing Project Structure",
    "Detecting Three-Tier Architecture",
    "Identifying Modules",
    "Analyzing Dependencies",
    "Building Migration Plan",
    "Analysis Completed"
  ];

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    _bindSidebarEvents();
    _bindFormControls();
    _bindActionButtons();

    // Listen to selection & navigation transitions to keep target indicator in sync
    EventBus.on('explorer:select', updateTargetIndicator);
    EventBus.on('tab:activate', updateTargetIndicator);
    EventBus.on('tab:switch', updateTargetIndicator);
    EventBus.on('file:open', updateTargetIndicator);
    EventBus.on('project:closed', closeWorkspace);

    updateTargetIndicator();
  }

  // ---------------------------------------------------------------------------
  // View Toggle / Workspace State
  // ---------------------------------------------------------------------------

  function openWorkspace() {
    _isOpen = true;
    
    // Toggle active accordion sidebar state
    const sidebarSec = document.getElementById('section-migration');
    if (sidebarSec) {
      sidebarSec.classList.remove('collapsed');
    }

    // Hide Monaco, Welcome, and Graph views
    const monacoContainer = document.getElementById('monaco-container');
    const welcomeEl = document.getElementById('editor-welcome');
    const graphContainer = document.getElementById('dependency-graph-container');
    const migrationContainer = document.getElementById('migration-workspace-container');

    if (welcomeEl) welcomeEl.style.display = 'none';
    if (monacoContainer) monacoContainer.style.display = 'none';
    if (graphContainer) graphContainer.style.display = 'none';
    if (migrationContainer) migrationContainer.style.display = 'block';

    // Remove active styling from editor tabs
    const activeTabs = document.querySelectorAll('.editor-tab.active');
    activeTabs.forEach(tab => tab.classList.remove('active'));

    updateTargetIndicator();
    Toast.show('Opened Migration Workspace', 'info', 2000);
  }

  function closeWorkspace() {
    _isOpen = false;
    _stopPolling();

    const migrationContainer = document.getElementById('migration-workspace-container');
    if (migrationContainer) migrationContainer.style.display = 'none';

    // Restore editor view based on active tab
    const activeTab = typeof TabBar !== 'undefined' ? TabBar.getActive() : null;
    const monacoContainer = document.getElementById('monaco-container');
    const welcomeEl = document.getElementById('editor-welcome');

    if (activeTab) {
      if (monacoContainer) monacoContainer.style.display = 'block';
      // Re-add active tab styling
      const tabEl = document.querySelector(`.editor-tab[data-path="${CSS.escape(activeTab)}"]`);
      if (tabEl) tabEl.classList.add('active');
    } else {
      if (welcomeEl) welcomeEl.style.display = 'flex';
    }

    if (typeof Editor !== 'undefined') Editor.layout();
  }

  function _onEditorFileOpen() {
    updateTargetIndicator();
  }

  function updateTargetIndicator() {
    const scopeRadio = document.querySelector('input[name="migration-scope"]:checked');
    const scope = scopeRadio ? scopeRadio.value : 'file';

    const targetBadgeEl = document.getElementById('migration-target-badge');
    const targetPathEl = document.getElementById('migration-target-path');
    const warningBoxEl = document.getElementById('migration-target-warning');
    const warningTextEl = document.getElementById('migration-target-warning-text');
    const targetBoxEl = document.getElementById('migration-target-box');
    const modeBadgeEl = document.getElementById('migration-mode-badge');
    const btnStart = document.getElementById('btn-migration-start');
    const orchStartBtn = document.getElementById('migration-start-btn');

    // Update mode badge (e.g. Python -> Java, Java -> Latest Version, Auto Detect -> Latest Version)
    const srcLangEl = document.getElementById('migration-source-lang');
    const tgtLangEl = document.getElementById('migration-target-lang');
    const srcVal = srcLangEl ? srcLangEl.value : 'auto';
    const tgtVal = tgtLangEl ? tgtLangEl.value : 'java';
    const srcText = srcLangEl ? srcLangEl.options[srcLangEl.selectedIndex].text : 'Auto Detect';
    const tgtText = tgtLangEl ? tgtLangEl.options[tgtLangEl.selectedIndex].text : 'Java';

    let modeDisplay = '';
    if (tgtVal === 'latest_version') {
      modeDisplay = `${srcText} → Latest Version`;
    } else {
      modeDisplay = `${srcText} → ${tgtText}`;
    }
    if (modeBadgeEl) modeBadgeEl.textContent = modeDisplay;

    let badgeText = '';
    let pathText = '';
    let isValid = true;
    let warningMsg = '';

    const activeFile = (typeof TabBar !== 'undefined' ? TabBar.getActive() : null) || (typeof Editor !== 'undefined' ? Editor.getActiveFilePath() : null);
    const selectedExplorerPath = typeof Explorer !== 'undefined' ? Explorer.getSelectedPath() : null;
    const selectedFolder = typeof Explorer !== 'undefined' ? Explorer.getSelectedFolder() : null;

    if (scope === 'file') {
      badgeText = 'Current File';
      if (activeFile) {
        pathText = activeFile;
        isValid = true;
      } else if (selectedExplorerPath && typeof Explorer !== 'undefined' && Explorer.getSelectedType() === 'file') {
        pathText = selectedExplorerPath;
        isValid = true;
      } else {
        pathText = 'No file open in editor';
        isValid = false;
        warningMsg = 'Open a file or select a folder to continue.';
      }
    } else if (scope === 'folder') {
      badgeText = 'Selected Folder';
      if (selectedFolder) {
        pathText = selectedFolder;
        isValid = true;
      } else {
        pathText = 'No folder selected in explorer';
        isValid = false;
        warningMsg = 'Open a file or select a folder to continue.';
      }
    } else if (scope === 'frontend') {
      badgeText = 'Frontend Layer';
      pathText = 'Frontend Layer (automatically detected)';
      isValid = true;
    } else if (scope === 'backend') {
      badgeText = 'Backend Layer';
      pathText = 'Backend Layer (automatically detected)';
      isValid = true;
    } else if (scope === 'database') {
      badgeText = 'Database Layer';
      pathText = 'Database Layer (automatically detected)';
      isValid = true;
    } else if (scope === 'project') {
      badgeText = 'Entire Project';
      pathText = 'Entire Project (Brownfield IDE)';
      isValid = true;
    }

    if (targetBadgeEl) targetBadgeEl.textContent = badgeText;
    if (targetPathEl) targetPathEl.textContent = pathText;

    if (!isValid) {
      if (targetBoxEl) targetBoxEl.classList.add('invalid');
      if (warningBoxEl) warningBoxEl.style.display = 'flex';
      if (warningTextEl) warningTextEl.textContent = warningMsg;
      if (btnStart) btnStart.disabled = true;
      if (orchStartBtn) orchStartBtn.disabled = true;
    } else {
      if (targetBoxEl) targetBoxEl.classList.remove('invalid');
      if (warningBoxEl) warningBoxEl.style.display = 'none';
      if (btnStart) btnStart.disabled = false;
      if (orchStartBtn) orchStartBtn.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // DOM Bindings
  // ---------------------------------------------------------------------------

  function _bindSidebarEvents() {
    const header = document.getElementById('header-migration');
    const sec = document.getElementById('section-migration');
    const btnSidebar = document.getElementById('btn-sidebar-open-migration');

    if (header && sec) {
      header.addEventListener('click', () => {
        sec.classList.toggle('collapsed');
        if (!sec.classList.contains('collapsed')) {
          openWorkspace();
        }
      });
    }

    if (btnSidebar) {
      btnSidebar.addEventListener('click', (e) => {
        e.stopPropagation();
        openWorkspace();
      });
    }
  }

  function _bindFormControls() {
    // Language selects
    const srcLangEl = document.getElementById('migration-source-lang');
    const tgtLangEl = document.getElementById('migration-target-lang');
    srcLangEl?.addEventListener('change', updateTargetIndicator);
    tgtLangEl?.addEventListener('change', updateTargetIndicator);

    // Custom radios
    const radios = document.querySelectorAll('input[name="migration-scope"]');
    radios.forEach(radio => {
      const parentLabel = radio.closest('.migration-radio-item');
      if (parentLabel) {
        parentLabel.addEventListener('click', () => {
          document.querySelectorAll('.migration-radio-item').forEach(item => {
            item.classList.remove('selected');
            const input = item.querySelector('input[type="radio"]');
            if (input) input.checked = false;
          });

          parentLabel.classList.add('selected');
          radio.checked = true;
          updateTargetIndicator();
        });
      }
    });

    // Custom checkboxes
    const checkboxes = document.querySelectorAll('input[name="migration-strategy"]');
    checkboxes.forEach(cb => {
      const parentLabel = cb.closest('.migration-checkbox-item');
      if (parentLabel) {
        parentLabel.addEventListener('click', (e) => {
          if (e.target !== cb) {
            cb.checked = !cb.checked;
          }
          parentLabel.classList.toggle('selected', cb.checked);
        });
      }
    });
  }

  function _bindActionButtons() {
    const btnStart = document.getElementById('btn-migration-start');
    const btnReset = document.getElementById('btn-migration-reset');
    const btnBack = document.getElementById('btn-migration-back');

    if (btnStart) {
      btnStart.addEventListener('click', startMigrationAnalysis);
    }

    if (btnReset) {
      btnReset.addEventListener('click', resetAnalysis);
    }

    if (btnBack) {
      btnBack.addEventListener('click', closeWorkspace);
    }
  }

  // ---------------------------------------------------------------------------
  // Real Backend Analysis Execution
  // ---------------------------------------------------------------------------

  async function startMigrationAnalysis() {
    _stopPolling();

    const rawSourceLang = document.getElementById('migration-source-lang')?.value || 'auto';
    const rawTargetLang = document.getElementById('migration-target-lang')?.value || 'java';

    let sourceLang = rawSourceLang;
    let targetLang = rawTargetLang;
    let sourceVer = null;
    let targetVer = null;

    if (rawTargetLang === 'latest_version') {
      targetLang = rawSourceLang !== 'auto' ? rawSourceLang : 'auto';
      targetVer = 'latest';
    }

    const scopeEl = document.querySelector('input[name="migration-scope"]:checked');
    const scope = scopeEl ? scopeEl.value : 'project';

    const strategies = [];
    document.querySelectorAll('input[name="migration-strategy"]:checked').forEach(cb => {
      strategies.push(cb.value);
    });

    // Determine target path for file/folder scopes
    let targetPath = null;
    if (scope === 'file') {
      targetPath = (typeof TabBar !== 'undefined' ? TabBar.getActive() : null) || (typeof Editor !== 'undefined' ? Editor.getActiveFilePath() : null) || (typeof Explorer !== 'undefined' ? Explorer.getSelectedPath() : null);
    } else if (scope === 'folder') {
      targetPath = typeof Explorer !== 'undefined' ? Explorer.getSelectedFolder() : null;
    }

    if ((scope === 'file' || scope === 'folder') && !targetPath) {
      Toast.show('Open a file or select a folder to continue.', 'warning');
      updateTargetIndicator();
      return;
    }

    // Remember the chosen configuration so Phase 3 generation can reuse it
    _lastConfig = { scope, targetPath, sourceLang, targetLang, strategies, sourceVer, targetVer, isLatestVersionMode: rawTargetLang === 'latest_version' };

    const btnStart = document.getElementById('btn-migration-start');
    const statusVal = document.getElementById('stat-current-status');
    const progressBar = document.getElementById('migration-progress-bar');
    const reportViewer = document.getElementById('migration-report-viewer');

    if (btnStart) btnStart.disabled = true;
    if (statusVal) {
      statusVal.textContent = "Analyzing Project...";
      statusVal.className = "migration-stat-value warning";
    }

    if (progressBar) progressBar.style.width = "5%";
    if (reportViewer) reportViewer.textContent = "Migration Analysis Engine running...";

    _renderProgressStepsLog([], "Project Loaded", 5.0);

    try {
      // Call Backend API Endpoint
      await API.migration.analyze(scope, targetPath, sourceLang, targetLang, strategies, sourceVer, targetVer);
      
      // Start real-time status polling
      _startPolling();

    } catch (err) {
      console.error('[Migration] Analysis trigger failed:', err);
      if (btnStart) btnStart.disabled = false;
      if (statusVal) {
        statusVal.textContent = "Failed";
        statusVal.className = "migration-stat-value error";
      }
      Toast.show(`Migration Analysis Failed: ${err.message}`, 'error');
    }
  }

  function _startPolling() {
    _stopPolling();
    _pollStatus();
    _pollInterval = setInterval(_pollStatus, 400);
  }

  function _stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  async function _pollStatus() {
    try {
      const data = await API.migration.status();
      
      const progressBar = document.getElementById('migration-progress-bar');
      const statusVal = document.getElementById('stat-current-status');
      const btnStart = document.getElementById('btn-migration-start');

      if (progressBar) {
        progressBar.style.width = `${Math.max(data.progress, 5)}%`;
      }

      _renderProgressStepsLog(data.step_logs, data.current_step, data.progress);

      if (data.status === 'completed') {
        _stopPolling();
        if (btnStart) btnStart.disabled = false;
        if (statusVal) {
          statusVal.textContent = "Analysis Completed";
          statusVal.className = "migration-stat-value success";
        }

        if (data.plan) {
          _populateSummary(data.plan);
          _renderReportMarkdown(data.plan.report_markdown);
        }
        Toast.show('Migration Analysis Completed — starting AI migration…', 'success');

        // Phase 3: hand the Migration Plan to the AI Migration Agent, which
        // generates migrated code into an isolated staging workspace. The
        // progress panel is taken over by the generation steps.
        if (typeof MigrationAgent !== 'undefined' && data.plan && _lastConfig) {
          MigrationAgent.begin(data.plan, _lastConfig);
        }

      } else if (data.status === 'failed') {
        _stopPolling();
        if (btnStart) btnStart.disabled = false;
        if (statusVal) {
          statusVal.textContent = "Failed";
          statusVal.className = "migration-stat-value error";
        }
        Toast.show(`Analysis error: ${data.error || 'Unknown error'}`, 'error');
      }

    } catch (err) {
      console.warn('[Migration] Poll failed:', err);
    }
  }

  function _renderProgressStepsLog(logs, currentStepName, currentProgress) {
    const stepsLog = document.getElementById('migration-steps-log');
    if (!stepsLog) return;

    stepsLog.innerHTML = "";

    ANALYSIS_STEPS.forEach((stepName, idx) => {
      const matchedLog = logs.find(l => l.step === stepName);
      let dotClass = "waiting";
      let timeText = "";

      if (matchedLog) {
        dotClass = "completed";
        timeText = matchedLog.timestamp || "";
      } else if (stepName === currentStepName || (idx === 0 && logs.length === 0)) {
        dotClass = "running";
      }

      const row = document.createElement('div');
      row.className = `migration-step-row${dotClass === 'running' ? ' active' : ''}`;
      row.innerHTML = `
        <span class="migration-step-dot ${dotClass}"></span>
        <span class="migration-step-text">${Helpers.escapeHtml(stepName)}</span>
        <span class="migration-step-time">${timeText}</span>
      `;
      stepsLog.appendChild(row);
    });
  }

  function _populateSummary(plan) {
    document.getElementById('stat-files-selected').textContent = plan.included_files_count || 0;
    document.getElementById('stat-files-converted').textContent = 0; // Phase 2 does NOT generate code
    document.getElementById('stat-warnings').textContent = 0;
    document.getElementById('stat-errors').textContent = 0;
  }

  function _renderReportMarkdown(markdownText) {
    const reportViewer = document.getElementById('migration-report-viewer');
    if (!reportViewer) return;

    if (!markdownText) {
      reportViewer.textContent = "No report content generated.";
      return;
    }

    // Convert Markdown headers, bold, code tags into clean HTML formatting
    let formatted = Helpers.escapeHtml(markdownText)
      .replace(/^# (.*$)/gim, '<div class="migration-report-header" style="font-size:1.2rem; margin-top:8px;">$1</div>')
      .replace(/^## (.*$)/gim, '<div class="migration-report-header" style="font-size:1rem; margin-top:12px; color:var(--color-cyan);">$1</div>')
      .replace(/^---$/gim, '<hr style="border:0; border-top:1px solid rgba(255,255,255,0.1); margin:10px 0;"/>')
      .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--color-text-primary);">$1</strong>')
      .replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.06); padding:1px 5px; border-radius:3px; color:var(--color-text-cyan); font-family:var(--font-code); font-size:11px;">$1</code>')
      .replace(/^- (.*$)/gim, '<div style="padding-left:10px; margin-bottom:2px;">• $1</div>')
      .replace(/^> (.*$)/gim, '<blockquote style="border-left:3px solid var(--color-accent); padding-left:8px; color:var(--color-text-accent); margin:8px 0;">$1</blockquote>');

    reportViewer.innerHTML = formatted;
  }

  function resetAnalysis() {
    _stopPolling();
    _lastConfig = null;

    // Also tear down any Phase 3 generation output.
    if (typeof MigrationAgent !== 'undefined') MigrationAgent.reset();

    const progressBar = document.getElementById('migration-progress-bar');
    const stepsLog = document.getElementById('migration-steps-log');
    const statusVal = document.getElementById('stat-current-status');
    const btnStart = document.getElementById('btn-migration-start');

    if (btnStart) btnStart.disabled = false;
    if (progressBar) progressBar.style.width = "0%";
    if (statusVal) {
      statusVal.textContent = "Idle";
      statusVal.className = "migration-stat-value";
    }

    if (stepsLog) {
      stepsLog.innerHTML = `
        <div class="migration-step-row" id="step-row-idle">
          <span class="migration-step-dot waiting"></span>
          <span class="migration-step-text">Waiting for Migration...</span>
        </div>
      `;
    }

    // Reset settings input forms
    const srcSelect = document.getElementById('migration-source-lang');
    const tgtSelect = document.getElementById('migration-target-lang');
    if (srcSelect) srcSelect.value = 'auto';
    if (tgtSelect) tgtSelect.value = 'java';

    // Reset radio scope controls
    document.querySelectorAll('.migration-radio-item').forEach(item => {
      item.classList.remove('selected');
      const input = item.querySelector('input[type="radio"]');
      if (input) input.checked = false;
    });
    const defaultRadio = document.getElementById('label-scope-file');
    if (defaultRadio) {
      defaultRadio.classList.add('selected');
      const input = defaultRadio.querySelector('input[type="radio"]');
      if (input) input.checked = true;
    }

    // Reset strategy checkboxes
    document.querySelectorAll('.migration-checkbox-item').forEach(item => {
      item.classList.remove('selected');
      const cb = item.querySelector('input[type="checkbox"]');
      if (cb) cb.checked = false;
    });
    
    ['label-strat-arch', 'label-strat-folder', 'label-strat-naming', 'label-strat-report'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add('selected');
        const cb = el.querySelector('input[type="checkbox"]');
        if (cb) cb.checked = true;
      }
    });

    // Clear stats
    document.getElementById('stat-files-selected').textContent = "-";
    document.getElementById('stat-files-converted').textContent = "-";
    document.getElementById('stat-warnings').textContent = "-";
    document.getElementById('stat-errors').textContent = "-";
    document.getElementById('migration-report-viewer').textContent = "No report generated yet. Choose settings and click 'Start Migration'.";
    
    Toast.show('Migration Configuration Reset', 'info');
  }

  return { init, openWorkspace, closeWorkspace };
})();
