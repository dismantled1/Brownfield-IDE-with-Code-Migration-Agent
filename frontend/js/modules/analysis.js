/**
 * analysis.js — Project Analysis & Understanding UI Module.
 *
 * Manages Project Overview and Project Statistics panels, triggers background
 * codebase scanning, updates progress bars, and renders metadata dashboards.
 */

const Analysis = (() => {
  let _pollInterval = null;
  let _activeProjectPath = null;

  function init() {
    _bindAccordion();

    // Listen for project lifecycle events
    EventBus.on('project:opened', ({ projectName, projectPath }) => {
      _activeProjectPath = projectPath;
      _triggerAnalysis();
    });

    EventBus.on('project:closed', () => {
      _activeProjectPath = null;
      _stopPolling();
      _clearUI();
    });

    EventBus.on('explorer:refresh', () => {
      if (_activeProjectPath) {
        _triggerAnalysis();
      }
    });
  }

  function _bindAccordion() {
    const sections = ['overview', 'statistics', 'files'];
    sections.forEach(sec => {
      const header = document.getElementById(`header-${sec}`);
      const panel = document.getElementById(`section-${sec}`);
      if (header && panel) {
        header.addEventListener('click', () => {
          panel.classList.toggle('collapsed');
        });
      }
    });
  }

  async function _triggerAnalysis() {
    try {
      _renderInitialLoading();
      
      // Call backend to trigger background analysis
      await API.analysis.analyze();
      
      // Start polling status
      _startPolling();
    } catch (err) {
      console.error('[Analysis] Trigger failed:', err);
      _renderError(err.message);
    }
  }

  function _startPolling() {
    _stopPolling();
    _pollStatus();
    _pollInterval = setInterval(_pollStatus, 800);
  }

  function _stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  async function _pollStatus() {
    try {
      const data = await API.analysis.status();
      
      _updateOverviewUI(data);
      _updateStatisticsUI(data);

      if (data.status === 'completed') {
        _stopPolling();
        EventBus.emit('analysis:completed', data);
      } else if (data.status === 'failed') {
        _stopPolling();
        EventBus.emit('analysis:failed', data);
      }
    } catch (err) {
      console.warn('[Analysis] Poll failed:', err);
      _stopPolling();
    }
  }

  function _updateOverviewUI(data) {
    const container = document.getElementById('overview-panel-content');
    if (!container) return;

    const path = data.project_path || '';
    const name = path.split(/[/\\]/).pop() || 'Project';
    
    // Inferred project type based on detected languages
    let projectType = 'Mixed Project';
    const langs = Object.keys(data.stats?.languages || {});
    if (langs.length === 1) {
      projectType = `${langs[0]} Project`;
    } else if (langs.length > 1) {
      projectType = `${langs[0]} & ${langs[1]} Project`;
    }

    let statusHtml = '';
    let progressHtml = '';
    
    if (data.status === 'analyzing') {
      statusHtml = `<span class="overview-val" style="color:var(--color-warning); background:rgba(245,158,11,0.1)">Analyzing...</span>`;
      progressHtml = `
        <div class="analysis-progress-wrapper">
          <div class="progress-label">
            <span>Parsing Codebase</span>
            <span>${Math.round(data.progress)}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: ${data.progress}%"></div>
          </div>
          <div class="progress-status-text" title="${data.current_file}">
            Scanning: ${data.current_file || 'reading files...'}
          </div>
        </div>
      `;
    } else if (data.status === 'completed') {
      statusHtml = `<span class="overview-val" style="color:var(--color-success); background:rgba(16,185,129,0.1)">Completed</span>`;
    } else if (data.status === 'failed') {
      statusHtml = `<span class="overview-val" style="color:var(--color-error); background:rgba(239,68,68,0.1)">Failed</span>`;
      progressHtml = `<div style="color:var(--color-error); font-size:11px; margin-top:5px;">Error: ${data.error}</div>`;
    } else {
      statusHtml = `<span class="overview-val">Idle</span>`;
    }

    // Languages breakdown HTML
    let langsHtml = '';
    const langStats = data.stats?.languages || {};
    if (Object.keys(langStats).length > 0) {
      langsHtml = `
        <div style="margin-top: var(--space-2)">
          <div class="overview-lbl" style="margin-bottom: var(--space-2);">DETECTED LANGUAGES</div>
          <div class="lang-list">
            ${Object.entries(langStats).map(([lang, pct]) => `
              <div class="lang-item">
                <div class="lang-info">
                  <span style="font-weight:var(--font-weight-medium);">${lang}</span>
                  <span style="color:var(--color-text-muted);">${pct}%</span>
                </div>
                <div class="lang-bar-track">
                  <div class="lang-bar-fill" style="width: ${pct}%; background-color: ${_getLanguageColor(lang)}"></div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <div class="overview-item">
        <span class="overview-lbl">Project Name</span>
        <span class="overview-val" style="max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${name}">${name}</span>
      </div>
      <div class="overview-item">
        <span class="overview-lbl">Project Type</span>
        <span class="overview-val" title="${projectType}">${projectType}</span>
      </div>
      <div class="overview-item">
        <span class="overview-lbl">Scanner Status</span>
        ${statusHtml}
      </div>
      ${progressHtml}
      ${langsHtml}
    `;
  }

  function _updateStatisticsUI(data) {
    const container = document.getElementById('statistics-panel-content');
    if (!container) return;

    if (data.status === 'idle') {
      container.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No metrics collected.</div>`;
      return;
    }

    const stats = data.stats || {};
    container.innerHTML = `
      <div class="stats-grid">
        <div class="stats-card">
          <span class="stats-val">${stats.files || 0}</span>
          <span class="stats-lbl">Files</span>
        </div>
        <div class="stats-card">
          <span class="stats-val">${stats.folders || 0}</span>
          <span class="stats-lbl">Folders</span>
        </div>
        <div class="stats-card">
          <span class="stats-val">${stats.modules || 0}</span>
          <span class="stats-lbl">Modules</span>
        </div>
        <div class="stats-card">
          <span class="stats-val">${stats.classes || 0}</span>
          <span class="stats-lbl">Classes</span>
        </div>
      </div>
      <div class="stats-card" style="width: 100%; margin-top: var(--space-1);">
        <span class="stats-val" style="color:var(--color-text-accent);">${stats.functions || 0}</span>
        <span class="stats-lbl">Functions & Methods</span>
      </div>
    `;
  }

  function _getLanguageColor(lang) {
    const colors = {
      'PYTHON': '#3572A5',
      'JAVASCRIPT': '#f1e05a',
      'TYPESCRIPT': '#3178c6',
      'JAVA': '#b07219',
      'HTML': '#e34c26',
      'CSS': '#563d7c',
      'JSON': '#29beb0'
    };
    return colors[lang.toUpperCase()] || 'var(--color-accent)';
  }

  function _renderInitialLoading() {
    const overview = document.getElementById('overview-panel-content');
    const stats = document.getElementById('statistics-panel-content');
    
    if (overview) {
      overview.innerHTML = `
        <div class="analysis-progress-wrapper">
          <div class="progress-label">
            <span>Analyzing Project...</span>
            <span>0%</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: 0%"></div>
          </div>
          <div class="progress-status-text">Locating code assets...</div>
        </div>
      `;
    }
    if (stats) {
      stats.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">Calculating project metrics...</div>`;
    }
  }

  function _renderError(msg) {
    const overview = document.getElementById('overview-panel-content');
    if (overview) {
      overview.innerHTML = `<div style="color:var(--color-error); padding: 5px 0;">Failed to analyze project: ${msg}</div>`;
    }
  }

  function _clearUI() {
    const overview = document.getElementById('overview-panel-content');
    const stats = document.getElementById('statistics-panel-content');
    if (overview) overview.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No project opened</div>`;
    if (stats) stats.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No project opened</div>`;
  }

  return { init };
})();
