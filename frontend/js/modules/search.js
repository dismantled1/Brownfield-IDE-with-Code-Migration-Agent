/**
 * search.js — Intelligent Search & Navigation UI Module.
 *
 * Manages the Search Results panel, visualizes statistics and result cards,
 * and handles direct line-number navigations in Monaco.
 */

const Search = (() => {
  let _activeProject = null;

  function init() {
    _bindAccordion();
    _clearUI();

    // Project lifecycle events
    EventBus.on('project:opened', ({ projectPath }) => {
      _activeProject = projectPath;
      _clearUI();
    });

    EventBus.on('project:closed', () => {
      _activeProject = null;
      _clearUI();
    });

    // Listen for search queries submitted from Chat or elsewhere
    EventBus.on('search:trigger', async ({ query }) => {
      if (!_activeProject) return;
      
      // Auto-expand search results accordion
      const searchPanel = document.getElementById('section-search-results');
      if (searchPanel) {
        searchPanel.classList.remove('collapsed');
      }

      _showLoading();

      try {
        const data = await API.search.query(query);
        _renderResults(data);
      } catch (err) {
        console.error('[Search] Query failed:', err);
        _renderError(err.message);
      }
    });
  }

  function _bindAccordion() {
    const header = document.getElementById('header-search-results');
    const panel = document.getElementById('section-search-results');
    if (header && panel) {
      header.addEventListener('click', () => {
        panel.classList.toggle('collapsed');
      });
    }
  }

  function _showLoading() {
    const container = document.getElementById('search-panel-content');
    if (!container) return;

    container.innerHTML = `
      <div class="analysis-progress-wrapper" style="background:rgba(6,182,212,0.05); border:1px solid rgba(6,182,212,0.15)">
        <div class="progress-label" style="color:var(--color-text-cyan)">
          <span>Searching Codebase...</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" style="width: 50%; background:linear-gradient(90deg, var(--color-cyan), var(--color-cyan-hover))"></div>
        </div>
        <div class="progress-status-text">Scanning indexes and API route maps...</div>
      </div>
    `;
  }

  function _renderResults(data) {
    const container = document.getElementById('search-panel-content');
    if (!container) return;

    const stats = data.stats || {};
    const results = data.results || [];

    if (results.length === 0) {
      container.innerHTML = `
        <div class="search-stats-summary" style="background:rgba(239,68,68,0.05); border-color:rgba(239,68,68,0.2); color:var(--color-error)">
          Found 0 matches
        </div>
        <div style="font-style:italic; color:var(--color-text-muted); text-align:center; padding:var(--space-4) 0;">
          No matching code assets found.
        </div>
      `;
      return;
    }

    // Assemble statistics summary text
    const statsText = [];
    if (stats.files > 0) statsText.push(`${stats.files} File${stats.files > 1 ? 's' : ''}`);
    if (stats.classes > 0) statsText.push(`${stats.classes} Class${stats.classes > 1 ? 'es' : ''}`);
    if (stats.functions > 0) statsText.push(`${stats.functions} Function${stats.functions > 1 ? 's' : ''}`);
    if (stats.apis > 0) statsText.push(`${stats.apis} API${stats.apis > 1 ? 's' : ''}`);

    const statsSummary = `Found: ${statsText.join(', ') || '0 results'}`;

    // Renders result list. All code-derived text is HTML-escaped, and navigation
    // targets are carried via data-* attributes (no inline JS string injection).
    const esc = Helpers.escapeHtml;
    const cardsHtml = results.map(res => {
      const type = esc(res.type || 'file');
      const name = esc(res.name || '');
      const reason = esc(res.reason || '');
      const file = res.file || '';
      const fileText = esc(res.line > 1 ? `${file} : Line ${res.line}` : file);
      const scorePct = res.score ? `Score: ${Math.round(res.score)}` : '';

      return `
        <div class="search-result-card" data-file="${esc(file)}" data-line="${res.line || 1}">
          <div class="search-result-header">
            <span class="search-result-title" title="${name}">${name}</span>
            <span class="search-result-badge ${type}">${type}</span>
          </div>
          <div class="search-result-reason" title="${reason}">${reason}</div>
          <div class="search-result-meta">
            <span style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${fileText}">${fileText}</span>
            ${scorePct ? `<span style="color:var(--color-text-cyan); font-weight:bold;">${scorePct}</span>` : ''}
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="search-stats-summary">${esc(statsSummary)}</div>
      <div class="search-results-list">${cardsHtml}</div>
    `;

    container.querySelectorAll('.search-result-card').forEach(card => {
      card.addEventListener('click', () => {
        navigateToResult(card.dataset.file, parseInt(card.dataset.line, 10) || 1);
      });
    });
  }

  function _renderError(msg) {
    const container = document.getElementById('search-panel-content');
    if (container) {
      container.innerHTML = `<div style="color:var(--color-error); padding: 5px 0;">Search failed: ${msg}</div>`;
    }
  }

  function _clearUI() {
    const container = document.getElementById('search-panel-content');
    if (container) {
      container.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No search run yet</div>`;
    }
  }

  // Public navigator called from card onclicks
  function navigateToResult(filepath, line) {
    if (typeof Editor !== 'undefined') {
      Editor.openAndHighlight(filepath, line);
    }
  }

  return { init, navigateToResult };
})();

// Bind globally for direct layout clicks
window.Search = Search;
